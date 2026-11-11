#!/usr/bin/env python3
"""Offline r-x object accounting from the four saved 02_steady smaps snapshots."""
import csv
import gzip
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BOOT = json.loads((ROOT / "data/prelink_overlay_prep/sources.json").read_text())
READELF = Path("/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf")
METRICS = ("Pss", "Rss", "Shared_Clean", "Private_Clean", "Private_Dirty", "SwapPss")
TARGETS = ("tvs-daemon", "tv-viewer")
PROCESS = re.compile(r"^###\s+(\d+)\s+(\S+)\s+(\S+)$")
MAPPING = re.compile(r"^[0-9a-f]+-[0-9a-f]+\s+([rwxps-]{4})\s+[0-9a-f]+\s+\S+\s+\d+\s*(.*?)\s*$")
METRIC = re.compile(r"^(Pss|Rss|Shared_Clean|Private_Clean|Private_Dirty|SwapPss):\s+(\d+)\s+kB$")
SO = re.compile(r"\.so(?:\.[^ /]+)?$")


def is_object(path, exe):
    return path == exe or bool(SO.search(path))


def category(exe, path, perms):
    seg = perms[:3]
    if path == exe and seg in ("r--", "rw-"):
        return "exe_" + seg
    if SO.search(path) and seg in ("r--", "rw-"):
        return "so_" + seg
    if not path or path == "[heap]" or path.startswith(("[anon", "[stack", "[tstack")):
        return "anonymous"
    return "other"


def parse(path):
    target = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    mappers = defaultdict(set)
    other = defaultdict(lambda: defaultdict(int))
    pid = name = exe = mapped = perms = None
    values = {}

    def flush():
        if mapped is None or pid is None:
            return
        if perms[:3] == "r-x" and mapped.startswith("/"):
            mappers[mapped].add(pid)
        if name not in TARGETS:
            return
        kind = category(exe, mapped, perms)
        if kind == "other":
            for k, v in values.items():
                other[name][k] += v
        if kind == "other" and perms[:3] == "r-x" and is_object(mapped, exe):
            for k, v in values.items():
                target[name][mapped][k] += v

    with gzip.open(path, "rt", errors="replace") as source:
        for raw in source:
            line = raw.rstrip("\n")
            match = PROCESS.match(line)
            if match:
                flush()
                pid, name, exe = int(match[1]), match[2], match[3]
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
    return target, mappers, other


def write_tsv(name, rows, fields):
    with (OUT / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def readelf(args, path):
    result = subprocess.run([str(READELF), *args, str(path)], capture_output=True, text=True, errors="replace", timeout=120)
    return result.returncode, result.stdout, result.stderr


def elf_features(image, object_path):
    path = ROOT / "data" / ("gcc_baseline" if image == "GCC" else "llvm_round3") / "elf/files" / object_path.lstrip("/")
    if not path.is_file():
        return {"status": "MISSING", "file": str(path.relative_to(ROOT))}
    results = {}
    for key, args in (("sections", ["-SW"]), ("segments", ["-lW"]), ("comment", ["-p", ".comment"]), ("symbols", ["-sW"])):
        rc, stdout, stderr = readelf(args, path)
        results[key] = {"rc": rc, "stdout": stdout, "stderr": stderr}
    # Keep the exact tool output for the selected top objects, including errors.
    name = f"readelf_{image}_{len(list(OUT.glob('readelf_*.txt'))):03d}.txt"
    (OUT / name).write_text("\n".join(f"### {key} rc={r['rc']}\n{r['stdout']}\nSTDERR:\n{r['stderr']}" for key, r in results.items()))
    sections = results["sections"]["stdout"]
    segments = results["segments"]["stdout"]
    text_bytes = 0
    has_symtab = False
    for line in sections.splitlines():
        m = re.search(r"\[\s*\d+\]\s+(\S+)\s+\S+\s+[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s", line)
        if not m:
            continue
        if m[1] == ".text":
            text_bytes += int(m[2], 16)
        if m[1] == ".symtab":
            has_symtab = True
    exec_load_bytes = 0
    for line in segments.splitlines():
        if line.lstrip().startswith("LOAD ") and re.search(r"\bR\s+E\b", line):
            parts = line.split()
            try:
                exec_load_bytes += int(parts[4], 16)
            except (IndexError, ValueError):
                pass
    symbols = results["symbols"]["stdout"]
    lto_trace = ".lto_priv." in symbols or ".gnu.lto" in sections
    lto = "有痕迹" if lto_trace else ("未见痕迹" if has_symtab else "无法判断（无 .symtab）")
    comment = results["comment"]["stdout"]
    return {"status": "OK" if results["sections"]["rc"] == 0 and results["segments"]["rc"] == 0 else "READELF_ERROR",
            "file": str(path.relative_to(ROOT)), "readelf_output": name,
            "text_bytes": text_bytes, "rx_load_filesz_bytes": exec_load_bytes,
            "has_symtab": has_symtab, "gcc_lto_trace": lto,
            "llvm_clang_comment": "是" if "clang" in comment.lower() else ("否" if results["comment"]["rc"] == 0 else "未确定（无 .comment）"),
            "readelf_error": " | ".join(f"{k}: {v['stderr'].strip()}" for k, v in results.items() if v["rc"] != 0)}


def main():
    print("readelf", READELF, flush=True)
    rc, version, error = readelf(["--version"], Path("/dev/null"))
    (OUT / "readelf_version.txt").write_text(f"rc={rc}\n{version}{error}")
    parsed = {}
    for boot, rel in BOOT.items():
        print("parse", boot, rel, flush=True)
        parsed[boot] = parse(ROOT / rel)
    perboot = []
    summary = []
    coverage = []
    objects = {name: set() for name in TARGETS}
    for boot in BOOT:
        target, mappers, other = parsed[boot]
        for name in TARGETS:
            for obj, values in target[name].items():
                objects[name].add(obj)
                row = {"boot": boot, "process": name, "object": obj, "mappers": len(mappers[obj]), "source": BOOT[boot]}
                row.update({k + "_kB": values[k] for k in METRICS})
                perboot.append(row)
            coverage.append({"boot": boot, "process": name,
                             "other_Pss_kB": other[name]["Pss"],
                             "object_rx_Pss_kB": sum(v["Pss"] for v in target[name].values()),
                             "other_residual_Pss_kB": other[name]["Pss"] - sum(v["Pss"] for v in target[name].values())})
    write_tsv("object_per_boot.tsv", perboot, ["boot", "process", "object", *[k + "_kB" for k in METRICS], "mappers", "source"])
    write_tsv("other_coverage.tsv", coverage, ["boot", "process", "other_Pss_kB", "object_rx_Pss_kB", "other_residual_Pss_kB"])
    for name in TARGETS:
        for obj in sorted(objects[name]):
            values = [[parsed[boot][0][name][obj][k] for boot in BOOT] for k in METRICS]
            counts = [len(parsed[boot][1].get(obj, set())) for boot in BOOT]
            row = {"process": name, "object": obj}
            for k, v in zip(METRICS, values):
                row.update({f"{boot}_{k}_kB": number for boot, number in zip(BOOT, v)})
                row.update({f"GCC_mean_{k}_kB": (v[0]+v[1])/2, f"LLVM_mean_{k}_kB": (v[2]+v[3])/2,
                            f"delta_{k}_kB": (v[2]+v[3]-v[0]-v[1])/2,
                            f"GCC_range_{k}_kB": abs(v[1]-v[0]), f"LLVM_range_{k}_kB": abs(v[3]-v[2])})
            row.update({f"{boot}_mappers": number for boot, number in zip(BOOT, counts)})
            row.update({"GCC_mean_mappers": (counts[0]+counts[1])/2, "LLVM_mean_mappers": (counts[2]+counts[3])/2,
                        "delta_mappers": (counts[2]+counts[3]-counts[0]-counts[1])/2})
            summary.append(row)
    summary.sort(key=lambda r: (r["process"], -r["delta_Pss_kB"], r["object"]))
    write_tsv("object_summary.tsv", summary, list(summary[0]))
    selected = {r["object"] for name in TARGETS for r in [x for x in summary if x["process"] == name][:10]}
    elfrows = []
    rpm = {}
    with (ROOT / "data/prelink_overlay_prep/library_union.tsv").open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rpm[row["path"]] = row["rpm"]
    rpm["/usr/bin/tvs-daemon"] = "tvs-main-loop-0.1.2-1.armv7l"
    rpm["/usr/apps/org.tizen.tv-viewer/bin/tv-viewer"] = "org.tizen.tv-viewer-0.3.8-1.armv7l"
    for obj in sorted(selected):
        for image in ("GCC", "LLVM"):
            print("ELF", image, obj, flush=True)
            features = elf_features(image, obj)
            row = {"image": image, "object": obj, "rpm": rpm.get(obj, "未找到"), **features}
            elfrows.append(row)
    fields = sorted({k for row in elfrows for k in row})
    write_tsv("top10_elf.tsv", elfrows, fields)
    (OUT / "sources.json").write_text(json.dumps({"boots": BOOT, "readelf": str(READELF), "rpm_source": "data/prelink_overlay_prep/library_union.tsv"}, ensure_ascii=False, indent=2) + "\n")
    print("DONE", len(perboot), "per-boot rows", len(summary), "object rows", len(elfrows), "ELF rows", flush=True)


if __name__ == "__main__":
    main()
