#!/usr/bin/env python3
"""Compare unique LLVM r-x file pages with two GCC per-file Pss sums."""
import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEMDIFF = HERE.parents[1]
BOOTS = json.loads((MEMDIFF / "data/prelink_overlay_prep/sources.json").read_text())
PROC = re.compile(r"^###\s+(\d+)\s+(\S+)\s+(\S+)$")
MAP = re.compile(r"^[0-9a-f]+-[0-9a-f]+\s+([rwxps-]{4})\s+[0-9a-f]+\s+\S+\s+\d+\s*(.*?)\s*$")
PSS = re.compile(r"^Pss:\s+(\d+)\s+kB$")
LOADER = {"dynsym", "dynstr", "hash", "gnu_version", "rel_dyn", "rel_plt"}


def read(name):
    with (HERE / name).open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def tsv(name, rows, fields):
    with (HERE / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def gcc_pss(path):
    total = defaultdict(int)
    mappers = defaultdict(set)
    pid = None
    mapped = None
    perms = None
    values = []
    def flush():
        if pid is not None and mapped and perms == "r-xp" and mapped.startswith("/"):
            total[mapped] += sum(values)
            mappers[mapped].add(pid)
    with gzip.open(path, "rt", errors="replace") as stream:
        for raw in stream:
            line = raw.rstrip("\r\n")
            match = PROC.match(line)
            if match:
                flush()
                pid = int(match[1]); mapped = None; perms = None; values = []
                continue
            match = MAP.match(line)
            if match:
                flush()
                perms = match[1]; mapped = match[2].removesuffix(" (deleted)"); values = []
                continue
            match = PSS.match(line)
            if match and mapped is not None:
                values.append(int(match[1]))
    flush()
    return total, mappers


def directories(conf):
    dirs = []
    for line in conf.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "-l" and parts[1].startswith("/"):
            dirs.append(parts[1].rstrip("/"))
    return dirs


def main():
    state = json.loads((HERE / "collection.json").read_text())
    if state.get("status") != "DONE" or not state.get("root_restored"):
        raise RuntimeError("board collection incomplete")
    page_size = state["page_size"]
    files = {r["path"]: r for r in read("files_from_pages.tsv")}
    elf = {(r["image"], r["path"]): r for r in read("elf_summary.tsv")}
    sections = defaultdict(list)
    for row in read("elf_sections.tsv"):
        sections[(row["image"], row["path"])].append((row["section"], row["group"], row["section_type"], int(row["file_offset"]), int(row["size_bytes"])))
    gcc = {}
    gcc_mappers = {}
    for boot in ("GCC1", "GCC2"):
        gcc[boot], gcc_mappers[boot] = gcc_pss(MEMDIFF / BOOTS[boot])
        print("parsed", boot, len(gcc[boot]), "paths", flush=True)
    residency = defaultdict(float)
    crossing = defaultdict(int)
    with gzip.open(HERE / "unique_pages.tsv.gz", "rt") as stream:
        for index, row in enumerate(csv.DictReader(stream, delimiter="\t"), 1):
            path = row["path"]
            if ("LLVM", path) not in sections:
                continue
            start = int(row["file_offset_bytes"])
            end = start + page_size
            covered = 0
            touched = 0
            for name, group, kind, sec_offset, sec_size in sections[("LLVM", path)]:
                if kind == "NOBITS":
                    continue
                overlap = max(0, min(end, sec_offset + sec_size) - max(start, sec_offset))
                if overlap:
                    residency[(path, name, group)] += overlap / 1024
                    covered += overlap
                    touched += 1
            if covered > page_size:
                raise RuntimeError(f"overlapping sections: {path} offset={start}")
            if covered < page_size:
                residency[(path, "<headers/padding/unassigned>", "other")] += (page_size - covered) / 1024
            if touched > 1:
                crossing[path] += 1
            if index % 100000 == 0:
                print("allocated", index, "unique pages", flush=True)
    detail = [{"path": path, "section": name, "group": group, "resident_kB": round(amount, 6)}
              for (path, name, group), amount in sorted(residency.items())]
    tsv("section_residency.tsv", detail, ["path", "section", "group", "resident_kB"])
    dirs = directories(state["prelink_conf"])
    if len(dirs) != 8:
        raise RuntimeError(f"expected 8 prelink.conf -l directories; got {len(dirs)}")
    (HERE / "prelink_dirs.json").write_text(json.dumps(dirs, indent=2) + "\n")
    rows = []
    allpaths = sorted(set(files) | set(gcc["GCC1"]) | set(gcc["GCC2"]))
    for path in allpaths:
        current = files.get(path)
        elf_current = elf.get(("LLVM", path))
        elf_gcc = elf.get(("GCC", path))
        reasons = []
        if current and current["dedup_exclusion"]:
            reasons.append(current["dedup_exclusion"])
        if elf_current and elf_current["DT_TEXTREL"] == "True":
            reasons.append("DT_TEXTREL")
        if current and not elf_current:
            reasons.append("missing_or_nonELF_current_copy")
        if current and ("LLVM", path) not in sections:
            reasons.append("missing_current_sections")
        if current and elf_current and (elf_current["section_readelf_rc"] != "0" or not sections.get(("LLVM", path))):
            reasons.append("current_section_readelf_incomplete")
        if current and (path in gcc["GCC1"] or path in gcc["GCC2"]):
            if not elf_gcc:
                reasons.append("missing_GCC_ELF_copy")
            elif elf_gcc["section_readelf_rc"] != "0" or not sections.get(("GCC", path)):
                reasons.append("GCC_section_readelf_incomplete")
        loader = sum(amount for (file, _, group), amount in residency.items() if file == path and group in LOADER)
        text = sum(amount for (file, _, group), amount in residency.items() if file == path and group == "text")
        unique = int(current["unique_Rss_kB"]) if current else 0
        gcc1, gcc2 = gcc["GCC1"].get(path, 0), gcc["GCC2"].get(path, 0)
        gcc_mean = (gcc1 + gcc2) / 2
        gcc_loader_size = sum(size for _, group, _, _, size in sections.get(("GCC", path), []) if group in LOADER) / 1024 if elf_gcc else None
        lower = loader - min(gcc_mean, gcc_loader_size) if gcc_loader_size is not None and current else None
        matched = current is not None and (path in gcc["GCC1"] or path in gcc["GCC2"])
        eligible = matched and not reasons and gcc_loader_size is not None
        rows.append({"path": path, "population": "common" if matched else "LLVM_only" if current else "GCC_only",
                     "eligible": eligible, "exclude_reasons": ",".join(reasons) if reasons else "",
                     "LLVM_unique_rx_Rss_kB": unique if current else "",
                     "LLVM_loader_resident_kB": round(loader, 6) if current else "",
                     "LLVM_without_loader_kB": round(unique - loader, 6) if current else "",
                     "LLVM_text_resident_kB": round(text, 6) if current else "",
                     "GCC1_rx_Pss_sum_kB": gcc1, "GCC2_rx_Pss_sum_kB": gcc2,
                     "GCC_mean_rx_Pss_sum_kB": gcc_mean,
                     "GCC_loader_sections_size_kB": round(gcc_loader_size, 6) if gcc_loader_size is not None else "MISSING",
                     "loader_growth_strict_lower_kB": round(lower, 6) if lower is not None else "",
                     "LLVM_nonloader_minus_GCC_kB": round(unique - loader - gcc_mean, 6) if current else "",
                     "in_prelink_dir": any(path.startswith(d + "/") for d in dirs),
                     "LLVM_mappers": int(current["mappers"]) if current else 0,
                     "GCC1_mappers": len(gcc_mappers["GCC1"].get(path, set())),
                     "GCC2_mappers": len(gcc_mappers["GCC2"].get(path, set())),
                     "cross_section_pages": crossing[path],
                     "rx_Private_Dirty_kB": current["rx_Private_Dirty_kB"] if current else ""})
    tsv("file_residency.tsv", rows, list(rows[0]))
    tsv("single_side_files.tsv", [r for r in rows if r["population"] != "common"], list(rows[0]))
    eligible_rows = [r for r in rows if r["eligible"]]
    summaries = []
    for label, subset in (("common_eligible", eligible_rows),
                          ("common_eligible_prelink_dirs", [r for r in eligible_rows if r["in_prelink_dir"]])):
        llvm = sum(float(r["LLVM_unique_rx_Rss_kB"]) for r in subset)
        gcc1 = sum(float(r["GCC1_rx_Pss_sum_kB"]) for r in subset)
        gcc2 = sum(float(r["GCC2_rx_Pss_sum_kB"]) for r in subset)
        loader = sum(float(r["LLVM_loader_resident_kB"]) for r in subset)
        lower = sum(float(r["loader_growth_strict_lower_kB"]) for r in subset)
        yes = sum(float(r["LLVM_nonloader_minus_GCC_kB"]) <= 0 for r in subset)
        summaries.append({"population": label, "files": len(subset), "LLVM_unique_rx_Rss_kB": round(llvm, 3),
                          "GCC1_rx_Pss_sum_kB": round(gcc1, 3), "GCC2_rx_Pss_sum_kB": round(gcc2, 3),
                          "GCC_mean_rx_Pss_sum_kB": round((gcc1 + gcc2) / 2, 3),
                          "LLVM_minus_GCC_mean_kB": round(llvm - (gcc1 + gcc2) / 2, 3),
                          "LLVM_loader_resident_kB": round(loader, 3),
                          "loader_growth_strict_lower_kB": round(lower, 3),
                          "nonloader_le_GCC_files": yes, "nonloader_gt_GCC_files": len(subset) - yes})
    tsv("summary.tsv", summaries, list(summaries[0]))
    violations = sorted([r for r in eligible_rows if float(r["LLVM_nonloader_minus_GCC_kB"]) > 0],
                        key=lambda r: -float(r["LLVM_nonloader_minus_GCC_kB"]))
    tsv("nonloader_gt_GCC_top20.tsv", violations[:20], list(rows[0]))
    # The weekly +5.168457 MiB line uses per-mapping Pss, not the page-union metric.
    weekly = MEMDIFF / "data/llvm_round3/analysis/clang_matched_paths_detail.tsv"
    with weekly.open() as stream:
        selected = {r["path"] for r in csv.DictReader(stream, delimiter="\t")
                    if r["population"] == "matched_all_four" and r["segment"] == "code_r-x" and r["metric"] == "Pss"}
    vmas = read("vmas.tsv")
    pss_current = sum(float(r["Pss_kB"]) for r in vmas if r["path"] in selected and r["Pss_kB"] != "")
    observed = {r["path"] for r in vmas if r["path"] in selected}
    weekly_values = {"source": str(weekly.relative_to(MEMDIFF)), "paths_in_historical_set": len(selected),
                     "paths_present_current": len(observed), "paths_absent_current": len(selected - observed),
                     "current_per_mapping_rx_Pss_sum_kB": round(pss_current, 3),
                     "GCC_historical_mean_kB": 140*1024}  # overwritten from saved summary row below
    with (MEMDIFF / "data/llvm_round3/analysis/clang_matched_paths_summary.tsv").open() as stream:
        baseline = next(r for r in csv.DictReader(stream, delimiter="\t")
                        if r["group"] == "matched_all_four" and r["segment"] == "code_r-x" and r["metric"] == "Pss")
    weekly_values["GCC_historical_mean_kB"] = float(baseline["GCC_mean"])
    weekly_values["LLVM3_historical_mean_kB"] = float(baseline["LLVM3_mean"])
    weekly_values["LLVM3_minus_GCC_kB"] = float(baseline["LLVM3_minus_GCC"])
    weekly_values["current_minus_GCC_historical_kB"] = round(pss_current - float(baseline["GCC_mean"]), 3)
    (HERE / "weekly_reconciliation.json").write_text(json.dumps(weekly_values, ensure_ascii=False, indent=2) + "\n")
    print("DONE", len(rows), "file rows", len(eligible_rows), "eligible common", flush=True)


if __name__ == "__main__":
    main()
