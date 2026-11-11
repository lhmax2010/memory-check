#!/usr/bin/env python3
"""Offline analysis of the read-only overlay and library-closure capture."""

import csv
import datetime as dt
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
RAW = HERE / "board"
MARKER = "__PREP_REMOTE_RC="


def clean(name):
    lines = (RAW / (name + ".stdout")).read_text(errors="replace").replace("\r", "").splitlines()
    return [line for line in lines if line and not line.startswith(MARKER)]


def write_tsv(name, fields, rows):
    with (HERE / name).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


mounts = json.loads((HERE / "overlay_mounts.json").read_text())
uppers = json.loads((HERE / "upperdirs.json").read_text())
identity = json.loads((RAW / "identity_checks.json").read_text())
date_line = clean("board_date")[0]
board_epoch = int(date_line.rsplit(" ", 1)[1])
board_tz = dt.datetime.strptime(date_line.rsplit(" ", 1)[0], "%Y-%m-%dT%H:%M:%S%z").tzinfo
uptime_seconds = float(clean("board_uptime")[0].split()[0])
boot_epoch = board_epoch - uptime_seconds
original_stat = clean("original_os_release_stat")[0].replace("\\t", "\t")
mtime_match = re.search(r"\b(\d{10})\b", original_stat)
if not mtime_match:
    raise ValueError("cannot parse original os-release mtime: " + original_stat)
original_epoch = int(mtime_match[1])
build_id = identity["build_id"]
build_digits = re.search(r"(20\d{10})$", build_id)
if not build_digits:
    raise ValueError("cannot parse BUILD_ID timestamp: " + build_id)
build_epoch = dt.datetime.strptime(build_digits[1], "%Y%m%d%H%M").replace(tzinfo=board_tz).timestamp()
timeline = {"build_id": build_id, "build_timestamp_interpretation": build_digits[1],
            "timezone_assumption": str(board_tz), "build_epoch_assumed": build_epoch,
            "original_os_release_mtime_epoch": original_epoch,
            "board_epoch": board_epoch, "uptime_seconds": uptime_seconds,
            "boot_epoch": boot_epoch, "boot_id": identity["boot_id"]}
(HERE / "timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")

inventory = []
comparisons = []
whiteouts = []
elf_magic = []
find_errors = []
for index, upper in enumerate(uppers):
    overlay = next((m for m in mounts if m.get("upperdir") == upper), None)
    mountpoint = overlay["mountpoint"] if overlay else "UNMAPPED"
    for line in clean(f"upper{index}_inventory"):
        if line.startswith("find:"):
            find_errors.append({"upper_index": index, "phase": "inventory", "error": line})
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            raise ValueError("bad inventory line: " + line)
        path, kind, size, epoch, human, mode = parts[:6]
        rel = path[len(upper):].lstrip("/") if path.startswith(upper) else path
        overlay_path = (mountpoint.rstrip("/") + "/" + rel) if rel else mountpoint
        row = {"upper_index": index, "upperdir": upper, "mountpoint": mountpoint,
               "path": path, "overlay_path": overlay_path, "type": kind,
               "size_bytes": size, "mtime_epoch": epoch, "mtime_text": human,
               "mode_octal": mode}
        inventory.append(row)
    compare_path = RAW / f"upper{index}_compare.stdout"
    if compare_path.exists():
        for line in clean(f"upper{index}_compare"):
            if line.startswith("find:"):
                find_errors.append({"upper_index": index, "phase": "compare", "error": line})
                continue
            parts = line.split("\t")
            if len(parts) != 7:
                raise ValueError("bad comparison line: " + line)
            path, lower, exists, size, digest, lower_size, lower_digest = parts
            state = "new_no_lower" if exists == "0" else (
                "identical" if size == lower_size and digest == lower_digest else "different")
            comparisons.append({"upper_index": index, "upper_path": path,
                                "lower_path": lower, "lower_exists": exists,
                                "upper_size_bytes": size, "upper_sha256": digest,
                                "lower_size_bytes": lower_size,
                                "lower_sha256": lower_digest, "comparison": state})
    for line in clean(f"upper{index}_whiteouts"):
        if line.startswith("find:"):
            find_errors.append({"upper_index": index, "phase": "whiteouts", "error": line})
            continue
        parts = line.replace("\\t", "\t").split("\t")
        if len(parts) == 3:
            whiteouts.append({"upper_index": index, "path": parts[0],
                              "major_hex": parts[1], "minor_hex": parts[2],
                              "is_overlay_whiteout_0_0": parts[1] == "0" and parts[2] == "0"})
    for p in sorted(RAW.glob(f"upper{index}_elf_magic_*.stdout")):
        for line in p.read_text(errors="replace").replace("\r", "").splitlines():
            if not line or line.startswith(MARKER):
                continue
            path, magic = line.split("\t", 1)
            elf_magic.append({"upper_index": index, "path": path,
                              "first_four_bytes_hex": magic.strip(),
                              "is_elf": magic.split() == ["7f", "45", "4c", "46"]})

write_tsv("upper_inventory.tsv", tuple(inventory[0]), inventory)
write_tsv("upper_file_comparisons.tsv", tuple(comparisons[0]) if comparisons else
          ("upper_index", "upper_path", "lower_path", "lower_exists", "upper_size_bytes",
           "upper_sha256", "lower_size_bytes", "lower_sha256", "comparison"), comparisons)
write_tsv("upper_whiteouts.tsv", tuple(whiteouts[0]) if whiteouts else
          ("upper_index", "path", "major_hex", "minor_hex", "is_overlay_whiteout_0_0"), whiteouts)
write_tsv("upper_elf_magic.tsv", tuple(elf_magic[0]) if elf_magic else
          ("upper_index", "path", "first_four_bytes_hex", "is_elf"), elf_magic)
write_tsv("upper_find_errors.tsv", ("upper_index", "phase", "error"), find_errors)

age = []
for row in inventory:
    if row["type"] == "d":
        continue
    epoch = float(row["mtime_epoch"])
    age.append({"path": row["path"], "overlay_path": row["overlay_path"],
                "type": row["type"], "mtime_text": row["mtime_text"],
                "before_build_assumed": epoch < build_epoch,
                "before_original_os_release": epoch < original_epoch,
                "before_this_boot": epoch < boot_epoch})
write_tsv("upper_age_flags.tsv", tuple(age[0]) if age else
          ("path", "overlay_path", "type", "mtime_text", "before_build_assumed",
           "before_original_os_release", "before_this_boot"), age)

closures = json.loads((HERE / "process_closures.json").read_text())
membership = []
for process, runs in closures.items():
    for run in runs:
        for path in run["libraries"]:
            membership.append({"process": process, "pid": run["pid"], "library": path})
write_tsv("closure_membership.tsv", ("process", "pid", "library"), membership)

directories = []
for line in clean("prelink_conf"):
    parts = line.split()
    if len(parts) == 2 and parts[0] == "-l":
        directories.append(parts[1].rstrip("/"))
metadata = {}
for output in sorted(RAW.glob("closure_metadata_*.stdout")):
    for line in output.read_text(errors="replace").replace("\r", "").splitlines():
        if not line or line.startswith(MARKER):
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            raise ValueError("bad library metadata: " + line)
        path, digest, rpm, etype, size = parts
        metadata[path] = {"path": path, "sha256": digest, "rpm": rpm,
                          "elf_type": {"2": "ET_EXEC", "3": "ET_DYN"}.get(etype.strip(), etype.strip()),
                          "size_bytes": size,
                          "under_prelink_conf": any(path.startswith(d + "/") for d in directories)}
expected = set((HERE / "library_union_paths.txt").read_text().splitlines())
if set(metadata) != expected:
    raise ValueError(f"metadata mismatch: expected={len(expected)} actual={len(metadata)}")
write_tsv("library_union.tsv", tuple(next(iter(metadata.values()))),
          [metadata[path] for path in sorted(metadata)])
(HERE / "prelink_conf_directories.json").write_text(json.dumps(directories, indent=2) + "\n")

summary = {"upperdirs": len(uppers), "inventory_entries": len(inventory),
           "find_permission_errors": len(find_errors),
           "regular_files": sum(x["type"] == "f" for x in inventory),
           "whiteouts_0_0": sum(x["is_overlay_whiteout_0_0"] for x in whiteouts),
           "system_elf_overrides": [x["path"] for x in elf_magic if x["is_elf"]],
           "comparison_counts": {state: sum(x["comparison"] == state for x in comparisons)
                                 for state in ("identical", "different", "new_no_lower")},
           "libraries_union": len(metadata),
           "libraries_outside_prelink_conf": sum(not x["under_prelink_conf"] for x in metadata.values()),
           "libraries_missing_or_unowned": sum(x["sha256"] == "MISSING" or x["rpm"] == "NOT_OWNED"
                                                for x in metadata.values())}
(HERE / "board_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
