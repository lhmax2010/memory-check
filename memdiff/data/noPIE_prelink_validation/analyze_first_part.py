#!/usr/bin/env python3
"""Recompute first-part metrics from the two saved collections; no board access."""
import csv
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEMDIFF = HERE.parents[1]
READ = "/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf"
VMA = re.compile(r"^([0-9a-f]+)-([0-9a-f]+)\s+([rwxps-]{4})\s+([0-9a-f]+)\s+\S+\s+\d+\s*(.*?)\s*$")
METRIC = re.compile(r"^(Pss|SwapPss|Private_Dirty):\s+(\d+)\s+kB$")
SECTION = re.compile(r"^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s")
LOADER = (".dynsym", ".dynstr", ".gnu.hash", ".hash", ".rel.dyn", ".rel.plt")
OBJECTS = {
 "tvs-daemon": ["/usr/lib/"+x for x in ("libtvs-api-native.so", "libtvs-dvb-si.so", "libtvs-iss.so",
                   "libtvs-util.so", "libtvs-dsm.so", "libtvs-b2b.so", "libtvs-dvbbase-scan.so",
                   "libtvs-atsc30-parser.so", "libtvs-ext.so", "libtvs-si.so")],
 "tv-viewer": ["/usr/apps/org.tizen.tv-viewer/bin/tv-viewer", "/usr/lib/libtvs-parser.so", "/usr/lib/libtvs-api.so"],
}


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write(path, data, fields):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


def parse_smaps(path):
    """Only the __SMAPS_BEGIN__/END part, preserving mapping path and metrics."""
    blocks, active, section = [], None, False
    with path.open(errors="replace") as stream:
        for raw in stream:
            line = raw.rstrip("\r\n")
            if line == "__SMAPS_BEGIN__":
                section = True
                continue
            if line == "__SMAPS_END__":
                break
            if not section:
                continue
            m = VMA.match(line)
            if m:
                active = {"start": m[1], "end": m[2], "perms": m[3],
                          "offset": int(m[4], 16), "path": m[5].removesuffix(" (deleted)"),
                          "Pss": 0, "SwapPss": 0, "Private_Dirty": 0}
                blocks.append(active)
            elif active:
                m = METRIC.match(line)
                if m:
                    active[m[1]] = int(m[2])
    return blocks


def sections(path):
    proc = subprocess.run([READ, "-SW", str(path)], stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, errors="replace", timeout=90)
    if proc.returncode:
        raise RuntimeError(f"readelf -SW {path}: {proc.stderr}")
    result = []
    for line in proc.stdout.splitlines():
        m = SECTION.match(line)
        if m and m[2] != "NOBITS":
            result.append((m[1], int(m[4], 16), int(m[5], 16)))
    return result


def loader_name(name):
    return name in LOADER or name.startswith(".gnu.version")


def main():
    classification = json.loads((MEMDIFF / "data/llvm_round3/analysis/classification.json").read_text())
    libraries = set(classification["GCC_prelinked_LLVM3_unmarked"])
    fifteen = set(classification["GCC_nonPIE"])
    assert len(libraries) == 410 and len(fifteen) == 15
    old_group = rows(MEMDIFF / "data/prelink_group_attribution/per_file.tsv")
    exclusive = {x["path"] for x in old_group if x["group"] == "乙"}
    assert len(exclusive) == 62
    metric_rows, object_rows, static_rows = [], [], []
    summary = {"build_id": "T-KSU2EJAKUC-0101-PERF-202611120549", "boots": {}}
    for boot in (1, 2):
        label = f"boot{boot}"
        base = HERE / "boots" / label
        coll = base / "collection"
        budget = base / "budget"
        state = json.loads((coll / "collection.json").read_text())
        if state["status"] != "DONE" or not state["root_restored"]:
            raise RuntimeError(f"{label} collection not complete")
        proc_budget = rows(budget / "process_budget.tsv")
        exe_by_pid = {int(x["pid"]): x["exe"] for x in proc_budget}
        pid_by_name = defaultdict(list)
        for x in proc_budget:
            pid_by_name[x["name"]].append(int(x["pid"]))
        totals = Counter()
        for proc in state["processes"]:
            if proc["status"] != "complete":
                continue
            pid = proc["pid"]
            exe = exe_by_pid.get(pid, "")
            group = "GCC_nonPIE_15" if exe in fifteen else "other"
            for v in parse_smaps(coll / proc["raw"]):
                totals["Pss_all"] += v["Pss"]
                totals["SwapPss_all"] += v["SwapPss"]
                if group == "GCC_nonPIE_15":
                    totals["Pss_15"] += v["Pss"]
                    totals["SwapPss_15"] += v["SwapPss"]
                path, perm = v["path"], v["perms"][:3]
                if path in libraries and perm in ("r--", "rw-"):
                    totals[f"lib410_{group}_{perm}_Private_Dirty"] += v["Private_Dirty"]
                if path == "[heap]" or path.startswith("[anon") or path.startswith("[stack") or path.startswith("[tstack") or not path:
                    totals["anonymous_Pss"] += v["Pss"]
                    totals["anonymous_SwapPss"] += v["SwapPss"]
                if path.startswith("[stack") or path.startswith("[tstack"):
                    totals["stack_Pss"] += v["Pss"]
                    totals["stack_SwapPss"] += v["SwapPss"]
        meminfo = (coll / "raw/snapshot_meminfo.stdout").read_text()
        match = re.search(r"^PageTables:\s+(\d+)\s+kB", meminfo, re.M)
        totals["PageTables"] = int(match[1]) if match else 0
        summary["boots"][label] = {"boot_id": state["identity"]["boot_id"], "capture_reason": state["capture_reason"],
                                     "capture_uptime_s": state["capture_uptime_s"], **totals}
        for metric, value in sorted(totals.items()):
            metric_rows.append({"boot": label, "metric": metric, "value_kB": value})
        file_budget = {x["path"]: x for x in rows(budget / "file_budget.tsv")}
        rx_cols = [x for x in next(iter(file_budget.values())) if x.startswith("rx_") and x.endswith("_Pss_kB")]
        exclusive_pss = sum(sum(float(file_budget[path][col]) for col in rx_cols)
                            for path in exclusive if path in file_budget)
        summary["boots"][label]["exclusive62_rx_Pss_kB"] = round(exclusive_pss, 3)
        for process, objects in OBJECTS.items():
            pids = pid_by_name.get(process, [])
            for path in objects:
                local = coll / "elf" / path.lstrip("/")
                if not local.exists() or not pids:
                    object_rows.append({"boot": label, "process": process, "path": path,
                                        "rx_Rss_kB": "MISSING", "rx_loader_resident_kB": "MISSING"})
                    continue
                sec = sections(local)
                present_offsets = set()
                for pid in pids:
                    item = next((x for x in state["processes"] if x["pid"] == pid and x["status"] == "complete"), None)
                    if not item:
                        continue
                    # The collector preserves each pagemap response in the per-PID raw file.
                    from importlib.util import spec_from_file_location, module_from_spec
                    spec = spec_from_file_location("parse_pages", MEMDIFF / "tools/image_budget/engine/parse_pages.py")
                    module = module_from_spec(spec)
                    spec.loader.exec_module(module)
                    records, issues = module.parse_process(coll / item["raw"], pid, state["page_size"])
                    if issues:
                        continue
                    for record in records:
                        if record["path"] == path and record["perms"] == "r-xp":
                            present_offsets.update(record["present_offsets"])
                loader = 0.0
                for offset in present_offsets:
                    for name, start, size in sec:
                        if loader_name(name):
                            loader += max(0, min(offset + 4096, start + size) - max(offset, start)) / 1024
                object_rows.append({"boot": label, "process": process, "path": path,
                                    "rx_Rss_kB": len(present_offsets) * 4,
                                    "rx_loader_resident_kB": round(loader, 6)})
        elf = {x["path"]: x for x in rows(budget / "elf_metrics.tsv")}
        old_elf = {x["path"]: x for x in rows(HERE / "llvm1111_budget/elf_metrics.tsv")}
        for path in sorted(set(OBJECTS["tvs-daemon"] + OBJECTS["tv-viewer"])):
            now, old = elf.get(path), old_elf.get(path)
            if now and old:
                static_rows.append({"boot": label, "path": path,
                    "new_text_bytes": now[".text_bytes"], "llvm1111_text_bytes": old[".text_bytes"],
                    "new_dynsym_bytes": now[".dynsym_bytes"], "llvm1111_dynsym_bytes": old[".dynsym_bytes"],
                    "new_rel_dyn_bytes": now[".rel.dyn_bytes"], "llvm1111_rel_dyn_bytes": old[".rel.dyn_bytes"]})
    write(HERE / "metrics_per_boot.tsv", metric_rows, ["boot", "metric", "value_kB"])
    write(HERE / "pagemap13_loader_residency.tsv", object_rows,
          ["boot", "process", "path", "rx_Rss_kB", "rx_loader_resident_kB"])
    write(HERE / "static_13_vs_llvm1111.tsv", static_rows,
          ["boot", "path", "new_text_bytes", "llvm1111_text_bytes", "new_dynsym_bytes",
           "llvm1111_dynsym_bytes", "new_rel_dyn_bytes", "llvm1111_rel_dyn_bytes"])
    (HERE / "first_part_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    from datetime import datetime
    status = "成功"
    try:
        main()
    except Exception:
        status = "失败"
        raise
    finally:
        print("已结束", datetime.now().isoformat(), "状态=" + status, flush=True)
