#!/usr/bin/env python3
"""Extract newly appearing signature/UEP lines from before/after log captures."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sys

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
PAIRS = ("attr", "same", "modified", "restore")
SOURCES = ("dmesg", "dlog_main", "dlog_system")
PATTERN = re.compile(r"signature|\bkuep\b|\buep\b|not signed|signing|integrity", re.I)

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def run():
    rows = []
    summary = {}
    for phase in PAIRS:
        for source in SOURCES:
            before = (RAW / f"{phase}_before_{source}.stdout").read_text(errors="replace").splitlines()
            after = (RAW / f"{phase}_after_{source}.stdout").read_text(errors="replace").splitlines()
            old = Counter(before)
            added = []
            for line in after:
                if old[line]: old[line] -= 1
                elif line and not line.startswith("__UEP_RC__"): added.append(line)
            matches = [x for x in added if PATTERN.search(x)]
            summary[f"{phase}.{source}"] = {"before_lines": len(before), "after_lines": len(after), "new_lines_by_multiset": len(added), "signature_related_new_lines": len(matches)}
            for line in matches:
                rows.append((phase, source, line))
            print(stamp(), phase, source, len(matches), "signature-related new lines", flush=True)
    with (HERE / "uep_log_delta.tsv").open("w") as f:
        f.write("phase\tsource\tline\n")
        for phase, source, line in rows:
            f.write(f"{phase}\t{source}\t{line.replace(chr(9), ' ')}\n")
    (HERE / "log_delta_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

if __name__ == "__main__":
    status = "成功"
    try:
        run()
    except BaseException:
        status = "失败"
        raise
    finally:
        print("已结束", stamp(), "状态=" + status, flush=True)
