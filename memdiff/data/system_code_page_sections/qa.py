#!/usr/bin/env python3
"""Cross-check the saved board capture and derived tables before publication."""
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parents[1] / "reports/system_code_page_sections.md"


def read(name):
    with (HERE / name).open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def main():
    board = json.loads((HERE / "collection.json").read_text())
    summary = read("summary.tsv")
    files = read("file_residency.tsv")
    vmas = read("vmas.tsv")
    sections = read("section_residency.tsv")
    elf = read("elf_summary.tsv")
    thirteen = read("thirteen_dynamic.tsv")
    per_file = defaultdict(float)
    for row in sections:
        per_file[row["path"]] += float(row["resident_kB"])
    eligible = [r for r in files if r["eligible"] == "True"]
    max_allocation_error = max(abs(float(r["LLVM_unique_rx_Rss_kB"]) - per_file[r["path"]]) for r in eligible)
    mismatched_vmas = [r for r in vmas if r["Rss_kB"] and int(r["present_pages"]) * board["page_size"] // 1024 != int(r["Rss_kB"])]
    hash_pairs = [r for r in board["pulled"] if r["status"] == "hash_match"]
    report = REPORT.read_text()
    checks = {
        "identity": all(board["checks"].values()),
        "board_restored": board["root_restored"] and board["boot_id_unchanged"],
        "sha_pairs": all(r["board_sha256"] == r["host_sha256"] for r in hash_pairs),
        "pagemap_matches_smaps": not mismatched_vmas,
        "section_allocation_conserved": max_allocation_error < 0.001,
        "eligible_count_matches_summary": len(eligible) == int(summary[0]["files"]),
        "prior_13_present": len(thirteen) == 13,
        "both_sides_elf_count": sum(r["image"] == "GCC" for r in elf) == 1463 and sum(r["image"] == "LLVM" for r in elf) == 1452,
        "report_has_no_template_tokens": "{len(" not in report and "{sum(" not in report,
    }
    result = {"time_utc": datetime.now(timezone.utc).isoformat(), "checks": checks,
              "vmas": len(vmas), "eligible_common_files": len(eligible),
              "hash_matched_files": len(hash_pairs), "max_section_allocation_error_kB": max_allocation_error,
              "pagemap_smaps_mismatched_vmas": len(mismatched_vmas)}
    (HERE / "qa.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if not all(checks.values()):
        raise RuntimeError(f"quality gate failed: {checks}")
    print("已结束", result["time_utc"], "状态=DONE", flush=True)


if __name__ == "__main__":
    main()
