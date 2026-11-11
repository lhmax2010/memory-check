#!/usr/bin/env python3
"""Summarize raw, read-only SDB captures without querying the board."""

import csv
import json
from pathlib import Path
import re


BASE = Path(__file__).resolve().parent
RAW = BASE / "board"
LEDGER = json.loads((RAW / "process_ledger.json").read_text())
SO = re.compile(r"\.so(?:\.[^ /]+)?(?:$| \(deleted\)$)")
HEADER = re.compile(r"^[0-9a-fA-F]+-[0-9a-fA-F]+\s")


def text(name):
    return (RAW / (name + ".stdout")).read_text(errors="replace").replace("\r", "")


def library_path(path):
    return path.endswith(".so") or bool(SO.search(path))


def mapped_libraries(maps):
    result = set()
    for line in maps.splitlines():
        if not HEADER.match(line):
            continue
        fields = line.split(None, 5)
        if len(fields) >= 6 and library_path(fields[5]):
            result.add(fields[5].removesuffix(" (deleted)"))
    return sorted(result)


def dirty_by_library(smaps):
    values = {}
    path = ""
    perms = ""
    for line in smaps.splitlines():
        if HEADER.match(line):
            fields = line.split(None, 5)
            perms = fields[1][:3]
            path = fields[5].removesuffix(" (deleted)") if len(fields) >= 6 else ""
            continue
        if line.startswith("Private_Dirty:") and library_path(path) and perms in ("r--", "rw-"):
            amount = int(line.split()[1])
            values.setdefault(path, {"r--": 0, "rw-": 0})[perms] += amount
    return values


def aux_secure(auxv):
    words = [int(x) for x in auxv.split()]
    pairs = list(zip(words[::2], words[1::2]))
    found = [value for key, value in pairs if key == 23]
    return found[0] if len(found) == 1 else None


summary = []
rows = []
for item in LEDGER:
    name, pid = item["name"], item["pid"]
    key = f"proc_{name}_{pid}"
    libs = mapped_libraries(text(key + "_maps"))
    (BASE / f"libraries_{name}.txt").write_text("\n".join(libs) + "\n")
    dirty = dirty_by_library(text(key + "_smaps"))
    for path in sorted(dirty):
        rows.append([name, pid, path, dirty[path]["r--"], dirty[path]["rw-"], sum(dirty[path].values())])
    fields = text(key + "_file_stat").split()
    mode = int(fields[0], 8)
    elf = int(text(key + "_elf_type").strip())
    result = {"name": name, "pid": pid, "exe": item["exe"],
              "unit_from_cgroup": item["unit_from_cgroup"],
              "rpm": text(key + "_rpm").strip(),
              "elf_type": {2: "ET_EXEC", 3: "ET_DYN"}.get(elf, f"other:{elf}"),
              "mode_octal": fields[0], "setuid": bool(mode & 0o4000),
              "setgid": bool(mode & 0o2000), "getcap": text(key + "_getcap").strip(),
              "AT_SECURE": aux_secure(text(key + "_auxv")),
              "mapped_so_unique": len(libs),
              "so_private_dirty_r--_kB": sum(v["r--"] for v in dirty.values()),
              "so_private_dirty_rw-_kB": sum(v["rw-"] for v in dirty.values())}
    summary.append(result)

with (BASE / "library_private_dirty.tsv").open("w", newline="") as f:
    writer = csv.writer(f, delimiter="\t")
    writer.writerow(["process", "pid", "library", "r--_Private_Dirty_kB", "rw-_Private_Dirty_kB", "sum_kB"])
    writer.writerows(rows)
(BASE / "process_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
for item in summary:
    print(item["name"], item["AT_SECURE"], item["mapped_so_unique"],
          item["so_private_dirty_r--_kB"], item["so_private_dirty_rw-_kB"])
