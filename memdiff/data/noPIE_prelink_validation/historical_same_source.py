#!/usr/bin/env python3
"""Stream four historical smaps archives with the new-image per-VMA counters."""
import csv
import gzip
import glob
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEMDIFF = HERE.parents[1]
VMA = re.compile(r"^([0-9a-f]+)-([0-9a-f]+)\s+([rwxps-]{4})\s+([0-9a-f]+)\s+\S+\s+\d+\s*(.*?)\s*$")
METRIC = re.compile(r"^(Pss|SwapPss|Private_Dirty):\s+(\d+)\s+kB$")


def find_archive(image, boot):
    pattern = str(MEMDIFF / f"data/{image}/boot{boot}/memcheck/*/02_steady/smaps_raw.txt.gz")
    found = glob.glob(pattern)
    if len(found) != 1:
        raise RuntimeError(f"archive count {len(found)}: {pattern}")
    return Path(found[0])


def calculate(path, libs, programs):
    out = Counter()
    exe = ""
    vma = None
    def flush():
        if vma is None:
            return
        path, perm, pss, swap, dirty = vma["path"], vma["perm"], vma["Pss"], vma["SwapPss"], vma["Private_Dirty"]
        group = "GCC_nonPIE_15" if exe in programs else "other"
        out["Pss_all"] += pss
        out["SwapPss_all"] += swap
        if group == "GCC_nonPIE_15":
            out["Pss_15"] += pss
            out["SwapPss_15"] += swap
        if path in libs and perm in ("r--", "rw-"):
            out[f"lib410_{group}_{perm}_Private_Dirty"] += dirty
        if path == "[heap]" or path.startswith("[anon") or path.startswith("[stack") or path.startswith("[tstack") or not path:
            out["anonymous_Pss"] += pss
            out["anonymous_SwapPss"] += swap
        if path.startswith("[stack") or path.startswith("[tstack"):
            out["stack_Pss"] += pss
            out["stack_SwapPss"] += swap
    with gzip.open(path, "rt", errors="replace") as stream:
        for line in stream:
            if line.startswith("### "):
                flush()
                vma = None
                bits = line.rstrip().split(" ", 3)
                exe = bits[3] if len(bits) == 4 else ""
                continue
            m = VMA.match(line)
            if m:
                flush()
                vma = {"path": m[5].removesuffix(" (deleted)"), "perm": m[3][:3],
                       "Pss": 0, "SwapPss": 0, "Private_Dirty": 0}
                continue
            m = METRIC.match(line)
            if m and vma is not None:
                vma[m[1]] = int(m[2])
    flush()
    return out


def main():
    cls = json.loads((MEMDIFF / "data/llvm_round3/analysis/classification.json").read_text())
    libs, programs = set(cls["GCC_prelinked_LLVM3_unmarked"]), set(cls["GCC_nonPIE"])
    rows = []
    for image in ("gcc_baseline", "llvm_round3"):
        for boot in (1, 2):
            path = find_archive(image, boot)
            print("PARSE", path, flush=True)
            values = calculate(path, libs, programs)
            for metric, value in sorted(values.items()):
                rows.append({"image": image, "boot": boot, "metric": metric, "value_kB": value,
                             "source": str(path.relative_to(MEMDIFF))})
    with (HERE / "historical_smaps_same_source.tsv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, ["image", "boot", "metric", "value_kB", "source"], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    status = "成功"
    try:
        main()
    except Exception:
        status = "失败"
        raise
    finally:
        print("已结束", datetime.now().isoformat(), "状态=" + status, flush=True)
