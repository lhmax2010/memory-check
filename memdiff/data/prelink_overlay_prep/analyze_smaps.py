#!/usr/bin/env python3
"""Offline component accounting for three processes in four saved smaps snapshots."""

import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path
import re


MEMDIFF = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
TARGETS = ("tvs-daemon", "tv-viewer", "TIFSDaemon")
BOOTS = {
    "GCC1": "data/gcc_baseline/boot1/memcheck/gcc_boot1_20261102_182343/02_steady/smaps_raw.txt.gz",
    "GCC2": "data/gcc_baseline/boot2/memcheck/gcc_boot2_20261102_192351/02_steady/smaps_raw.txt.gz",
    "LLVM1": "data/llvm_round3/boot1/memcheck/llvm_boot1_20261103_015124/02_steady/smaps_raw.txt.gz",
    "LLVM2": "data/llvm_round3/boot2/memcheck/llvm_boot2_20261103_030258/02_steady/smaps_raw.txt.gz",
}
CATEGORIES = ("exe_r--", "exe_rw-", "so_r--", "so_rw-", "anonymous", "other")
PROCESS = re.compile(r"^###\s+(\d+)\s+(\S+)\s+(\S+)$")
MAPPING = re.compile(r"^[0-9a-f]+-[0-9a-f]+\s+([rwxps-]{4})\s+[0-9a-f]+\s+\S+\s+\d+\s*(.*?)\s*$")
METRIC = re.compile(r"^(Private_Dirty|Pss|SwapPss):\s+(\d+)\s+kB$")
SO = re.compile(r"\.so(?:\.[^ /]+)?(?:$| \(deleted\)$)")


def is_so(path):
    return bool(SO.search(path))


def category(exe, path, perms):
    seg = perms[:3]
    if path == exe and seg in ("r--", "rw-"):
        return "exe_" + seg
    if is_so(path) and seg in ("r--", "rw-"):
        return "so_" + seg
    if not path or path == "[heap]" or path.startswith(("[anon", "[stack", "[tstack")):
        return "anonymous"
    return "other"


def parse(path):
    totals = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    metadata = {}
    libraries = defaultdict(set)
    current_name = current_exe = mapped = perms = None
    values = {}

    def flush():
        if current_name in TARGETS and mapped is not None:
            kind = category(current_exe, mapped, perms)
            for metric, amount in values.items():
                totals[current_name][kind][metric] += amount
            if is_so(mapped):
                libraries[current_name].add(mapped.removesuffix(" (deleted)"))

    with gzip.open(path, "rt", errors="replace") as source:
        for raw in source:
            line = raw.rstrip("\n")
            match = PROCESS.match(line)
            if match:
                flush()
                current_name = match[2]
                current_exe = match[3]
                if current_name in TARGETS:
                    if current_name in metadata:
                        raise ValueError(f"duplicate target {current_name} in {path}")
                    metadata[current_name] = {"pid": int(match[1]), "exe": current_exe}
                mapped = perms = None
                values = {}
                continue
            match = MAPPING.match(line)
            if match:
                flush()
                perms = match[1]
                mapped = match[2].removesuffix(" (deleted)")
                values = {}
                continue
            match = METRIC.match(line)
            if match and mapped is not None:
                values[match[1]] = int(match[2])
    flush()
    if set(metadata) != set(TARGETS):
        raise ValueError(f"target presence mismatch in {path}: {set(metadata)}")
    return totals, metadata, libraries


def tsv(path, fields, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parsed = {}
    perboot = []
    for boot, relative in BOOTS.items():
        print("parse", boot, relative, flush=True)
        totals, metadata, libraries = parse(MEMDIFF / relative)
        parsed[boot] = {"totals": totals, "metadata": metadata, "libraries": libraries}
        for name in TARGETS:
            expected = sum(totals[name][kind]["Private_Dirty"] for kind in CATEGORIES)
            for kind in CATEGORIES:
                row = {"boot": boot, "process": name, "pid": metadata[name]["pid"],
                       "exe": metadata[name]["exe"], "component": kind,
                       "source": relative}
                row.update({key + "_kB": totals[name][kind][key]
                            for key in ("Private_Dirty", "Pss", "SwapPss")})
                perboot.append(row)
            if expected < 0:
                raise AssertionError("negative Private_Dirty")
    fields = ("boot", "process", "pid", "exe", "component", "Private_Dirty_kB",
              "Pss_kB", "SwapPss_kB", "source")
    tsv(OUT / "components_per_boot.tsv", fields, perboot)

    summary = []
    estimates = []
    for name in TARGETS:
        for kind in CATEGORIES:
            values = [parsed[boot]["totals"][name][kind]["Private_Dirty"] for boot in BOOTS]
            gcc = (values[0] + values[1]) / 2
            llvm = (values[2] + values[3]) / 2
            summary.append({"process": name, "component": kind,
                            "GCC1_kB": values[0], "GCC2_kB": values[1],
                            "LLVM1_kB": values[2], "LLVM2_kB": values[3],
                            "GCC_mean_kB": gcc, "LLVM_mean_kB": llvm,
                            "LLVM_minus_GCC_kB": llvm - gcc,
                            "GCC_range_kB": abs(values[1] - values[0]),
                            "LLVM_range_kB": abs(values[3] - values[2])})
        file_dirty = []
        totals = []
        for boot in BOOTS:
            by_kind = parsed[boot]["totals"][name]
            file_dirty.append(sum(by_kind[k]["Private_Dirty"] for k in CATEGORIES[:4]))
            totals.append(sum(by_kind[k]["Pss"] + by_kind[k]["SwapPss"] for k in CATEGORIES))
        file_delta = (file_dirty[2] + file_dirty[3] - file_dirty[0] - file_dirty[1]) / 2
        total_delta = (totals[2] + totals[3] - totals[0] - totals[1]) / 2
        estimates.append({"process": name, "GCC1_file_dirty_kB": file_dirty[0],
                          "GCC2_file_dirty_kB": file_dirty[1],
                          "LLVM1_file_dirty_kB": file_dirty[2],
                          "LLVM2_file_dirty_kB": file_dirty[3],
                          "file_dirty_delta_kB": file_delta,
                          "GCC1_total_Pss_plus_SwapPss_kB": totals[0],
                          "GCC2_total_Pss_plus_SwapPss_kB": totals[1],
                          "LLVM1_total_Pss_plus_SwapPss_kB": totals[2],
                          "LLVM2_total_Pss_plus_SwapPss_kB": totals[3],
                          "total_delta_kB": total_delta,
                          "ratio_file_dirty_to_total_delta": file_delta / total_delta if total_delta else "UNDEFINED"})
    tsv(OUT / "components_summary.tsv", tuple(summary[0]), summary)
    tsv(OUT / "file_dirty_vs_total.tsv", tuple(estimates[0]), estimates)

    lib_rows = []
    diff_rows = []
    for name in TARGETS:
        sets = [parsed[boot]["libraries"][name] for boot in BOOTS]
        for boot, libraries in zip(BOOTS, sets):
            for library in sorted(libraries):
                lib_rows.append({"boot": boot, "process": name, "library": library})
        for label, left, right in (("boot1", sets[0], sets[2]),
                                   ("boot2", sets[1], sets[3]),
                                   ("two_boot_union", sets[0] | sets[1], sets[2] | sets[3])):
            for side, members in (("GCC_only", left - right), ("LLVM_only", right - left)):
                for library in sorted(members):
                    diff_rows.append({"process": name, "comparison": label,
                                      "side": side, "library": library})
    tsv(OUT / "library_sets.tsv", ("boot", "process", "library"), lib_rows)
    tsv(OUT / "library_set_differences.tsv", ("process", "comparison", "side", "library"), diff_rows)
    (OUT / "sources.json").write_text(json.dumps(BOOTS, indent=2) + "\n")
    print("DONE components", len(perboot), "library differences", len(diff_rows), flush=True)


if __name__ == "__main__":
    main()
