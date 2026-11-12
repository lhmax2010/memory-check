#!/usr/bin/env python3
"""Parse saved per-PID board output into deduplicated file-offset page sets."""
import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEADER = re.compile(r"^([0-9a-f]+)-([0-9a-f]+)\s+([rwxps-]{4})\s+([0-9a-f]+)\s+(\S+)\s+(\d+)\s*(.*?)\s*$")
START = re.compile(r"^__PAGE_BEGIN__\t([^\t]+)\t([^\t]+)\t([^\t]+)\t(.+?)\t(\d+)$")
METRIC = re.compile(r"^(Rss|Pss|Private_Dirty):\s+(\d+)\s+kB$")


def tsv(name, rows, fields):
    with (HERE / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_process(path, pid, page_size):
    section = ""
    maps = {}
    smaps = {}
    active = None
    page = None
    words = []
    records = []
    issues = []
    saw_done = False
    with path.open(errors="replace") as stream:
        for raw in stream:
            line = raw.rstrip("\r\n")
            if line == "__MAPS_BEGIN__":
                section = "maps"; continue
            if line == "__MAPS_END__":
                section = ""; continue
            if line == "__SMAPS_BEGIN__":
                section = "smaps"; continue
            if line == "__SMAPS_END__":
                section = ""; continue
            if line == "__DONE__":
                saw_done = True; continue
            if section == "maps":
                m = HEADER.match(line)
                if m:
                    maps[m[1] + "-" + m[2]] = {"perms": m[3], "offset": m[4], "dev": m[5], "inode": m[6], "path": m[7]}
                continue
            if section == "smaps":
                m = HEADER.match(line)
                if m:
                    active = m[1] + "-" + m[2]
                    smaps[active] = {}
                    continue
                m = METRIC.match(line)
                if m and active:
                    smaps[active][m[1]] = int(m[2])
                continue
            m = START.match(line)
            if m:
                if page is not None:
                    issues.append("nested PAGE_BEGIN")
                page = {"address": m[1], "perms": m[2], "offset": m[3],
                        "path": m[4], "pages": int(m[5])}
                words = []
                continue
            if line.startswith("__PAGE_END__\t"):
                if page is None:
                    issues.append("PAGE_END without begin")
                    continue
                try:
                    remote_rc = int(line.split("\t", 1)[1])
                except ValueError:
                    remote_rc = -1
                if remote_rc or len(words) != page["pages"]:
                    issues.append(f"{page['address']}: dd rc={remote_rc}, got {len(words)}/{page['pages']}")
                else:
                    meta = maps.get(page["address"])
                    metrics = smaps.get(page["address"], {})
                    if not meta or meta["offset"].lower() != page["offset"].lower():
                        issues.append(f"{page['address']}: maps metadata missing/mismatch")
                    else:
                        present = [i for i, value in enumerate(words) if value >> 63 & 1]
                        swapped = sum(1 for value in words if value >> 62 & 1)
                        records.append({"pid": pid, "address": page["address"], "path": page["path"],
                                        "perms": page["perms"], "offset": int(page["offset"], 16),
                                        "dev": meta["dev"], "inode": meta["inode"],
                                        "present_offsets": [int(page["offset"], 16) + i * page_size for i in present],
                                        "present_pages": len(present), "swapped_pages": swapped,
                                        "Private_Dirty_kB": metrics.get("Private_Dirty"),
                                        "Rss_kB": metrics.get("Rss"), "Pss_kB": metrics.get("Pss")})
                page = None
                continue
            if page is not None:
                for token in line.split():
                    try:
                        words.append(int(token, 16))
                    except ValueError:
                        issues.append(f"{page['address']}: invalid pagemap token {token!r}")
    if not saw_done or page is not None:
        issues.append("missing DONE or unfinished page")
    return records, issues


def main():
    state = json.loads((HERE / "collection.json").read_text())
    if state.get("status") != "DONE" or not state.get("root_restored"):
        raise RuntimeError("collection incomplete or root restoration unconfirmed")
    page_size = state["page_size"]
    pages = defaultdict(set)
    mappers = defaultdict(set)
    identities = defaultdict(set)
    dirty = defaultdict(int)
    deleted_paths = set()
    missing_metrics = set()
    vmas = []
    errors = []
    for index, process in enumerate(state["processes"], 1):
        if process["status"] != "complete":
            errors.append({"pid": process["pid"], "issue": process["status"]})
            continue
        records, issues = parse_process(HERE / process["raw"], process["pid"], page_size)
        if issues:
            errors.extend({"pid": process["pid"], "issue": value} for value in issues)
            continue  # A process that exits or fails mid-capture is not retried.
        for record in records:
            deleted = record["path"].endswith(" (deleted)")
            path = record["path"].removesuffix(" (deleted)")
            record["path"] = path
            record["deleted_mapping"] = deleted
            if deleted:
                deleted_paths.add(path)
            if any(record[key] is None for key in ("Private_Dirty_kB", "Rss_kB", "Pss_kB")):
                missing_metrics.add(path)
            pages[path].update(record.pop("present_offsets"))
            mappers[path].add(process["pid"])
            identities[path].add((record["dev"], record["inode"]))
            dirty[path] += record["Private_Dirty_kB"] or 0
            vmas.append(record)
        if index % 25 == 0:
            print("parsed", index, "/", len(state["processes"]), "files", len(pages), flush=True)
    tsv("vmas.tsv", vmas, list(vmas[0]) if vmas else ["pid", "path"])
    tsv("process_parse_errors.tsv", errors, ["pid", "issue"])
    identity_paths = defaultdict(set)
    for path, keys in identities.items():
        for key in keys:
            identity_paths[key].add(path)
    alias_rows = [{"dev": dev, "inode": inode, "paths": " | ".join(sorted(names))}
                  for (dev, inode), names in sorted(identity_paths.items()) if len(names) > 1]
    tsv("inode_path_aliases.tsv", alias_rows, ["dev", "inode", "paths"])
    files = []
    for path in sorted(pages):
        flags = []
        if dirty[path] > 0:
            flags.append("rx_Private_Dirty")
        if len(identities[path]) > 1:
            flags.append("multiple_dev_inode")
        if path in deleted_paths:
            flags.append("deleted_mapping")
        if path in missing_metrics:
            flags.append("missing_smaps_metric")
        if any(len(identity_paths[key]) > 1 for key in identities[path]):
            flags.append("same_inode_multiple_paths")
        files.append({"path": path, "unique_present_pages": len(pages[path]),
                      "unique_Rss_kB": len(pages[path]) * page_size // 1024,
                      "mappers": len(mappers[path]), "rx_Private_Dirty_kB": dirty[path],
                      "dev_inode_count": len(identities[path]), "dedup_exclusion": ",".join(flags)})
    tsv("files_from_pages.tsv", files, list(files[0]))
    with gzip.open(HERE / "unique_pages.tsv.gz", "wt") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("path", "file_offset_bytes"))
        for path in sorted(pages):
            for offset in sorted(pages[path]):
                writer.writerow((path, offset))
    print("DONE", len(vmas), "VMAs", len(files), "files", len(errors), "process issues", flush=True)


if __name__ == "__main__":
    main()
