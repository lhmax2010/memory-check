#!/usr/bin/env python3
"""Allocate pagemap-present file pages to ELF sections by file-byte overlap."""
import csv
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
MEMDIFF = OUT.parents[1]
READELF = Path("/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf")
SECTION = re.compile(r"^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s")
MAP = re.compile(r"^([0-9a-f]+)-([0-9a-f]+)\s+([rwxps-]{4})\s+([0-9a-f]+)\s+\S+\s+\d+\s*(.*?)\s*$")
SMAPS_METRIC = re.compile(r"^(Rss|Pss|Private_Dirty):\s+(\d+)\s+kB$")
LOADER = {"dynsym", "dynstr", "hash", "gnu_version", "rel_dyn", "rel_plt"}
GROUPS = ("text", "rodata", "arm_unwind", "eh_frame", "dynsym", "dynstr", "hash",
          "gnu_version", "rel_dyn", "rel_plt", "plt", "data_rel_ro", "got", "data", "bss", "other")


def group(name):
    if name.startswith(".text"):
        return "text"
    if name.startswith(".rodata"):
        return "rodata"
    if name.startswith(".ARM.exidx") or name.startswith(".ARM.extab"):
        return "arm_unwind"
    if name.startswith(".eh_frame") or name == ".gcc_except_table":
        return "eh_frame"
    if name == ".dynsym":
        return "dynsym"
    if name == ".dynstr":
        return "dynstr"
    if name in (".gnu.hash", ".hash"):
        return "hash"
    if name.startswith(".gnu.version"):
        return "gnu_version"
    if name in (".rel.dyn", ".rela.dyn", ".relr.dyn"):
        return "rel_dyn"
    if name in (".rel.plt", ".rela.plt"):
        return "rel_plt"
    if name.startswith(".plt"):
        return "plt"
    if name.startswith(".data.rel.ro"):
        return "data_rel_ro"
    if name in (".got", ".got.plt"):
        return "got"
    if name == ".data" or name.startswith(".data.") or name == ".sdata":
        return "data"
    if name in (".bss", ".tbss") or name.startswith(".bss."):
        return "bss"
    return "other"


def readelf(path, label):
    results = {}
    for flag, suffix in (("-SW", "sections"), ("-lW", "segments")):
        run = subprocess.run([str(READELF), flag, str(path)], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, errors="replace", timeout=120)
        (OUT / "readelf" ).mkdir(exist_ok=True)
        (OUT / "readelf" / f"{label}.{suffix}.txt").write_text(f"rc={run.returncode}\n{run.stdout}\nSTDERR:\n{run.stderr}")
        if run.returncode:
            raise RuntimeError(f"readelf {flag} {path}: rc={run.returncode}: {run.stderr}")
        results[suffix] = run.stdout
    sections = []
    for line in results["sections"].splitlines():
        match = SECTION.match(line)
        if not match:
            continue
        name, kind, _, offset, size = match.groups()
        sections.append({"name": name, "type": kind, "offset": int(offset, 16),
                         "size": int(size, 16), "group": group(name)})
    if not sections:
        raise RuntimeError(f"no ELF sections parsed from {path}")
    loads = []
    for line in results["segments"].splitlines():
        if not line.lstrip().startswith("LOAD "):
            continue
        parts = line.split()
        if len(parts) < 8:
            raise RuntimeError(f"unparseable LOAD: {line}")
        flags = "".join(parts[6:-1])
        loads.append({"offset": int(parts[1], 16), "filesz": int(parts[4], 16),
                      "memsz": int(parts[5], 16), "flags": flags})
    return sections, loads


def smaps_blocks(text):
    blocks = {}
    key = None
    metrics = {}
    def flush():
        if key is not None:
            blocks[key] = dict(metrics)
    for line in text.splitlines():
        m = MAP.match(line)
        if m:
            flush()
            key = (int(m[1], 16), int(m[2], 16), int(m[4], 16), m[3], m[5].removesuffix(" (deleted)"))
            metrics = {}
            continue
        m = SMAPS_METRIC.match(line)
        if m and key is not None:
            metrics[m[1]] = int(m[2])
    flush()
    return blocks


def write(name, rows, fields):
    with (OUT / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    collection = json.loads((OUT / "collection.json").read_text())
    if not all(collection.get("checks", {}).values()) or not collection.get("root_restored"):
        raise RuntimeError("identity gate or root restoration not confirmed")
    page_size = collection["page_size"]
    objects = sorted({m["path"] for m in collection["mappings"]})
    pulled = {x["path"]: OUT / x["local"] for x in collection["pulled"]}
    missing = set(objects) - set(pulled)
    if missing:
        raise RuntimeError(f"missing pulled ELF: {sorted(missing)}")
    llvm3_rows = []
    for path in objects:
        old = MEMDIFF / "data/llvm_round3/elf/files" / path.lstrip("/")
        llvm3_rows.append({"object": path, "current_sha256": sha(pulled[path]),
                           "LLVM3_sha256": sha(old) if old.is_file() else "MISSING",
                           "same_bytes": old.is_file() and sha(pulled[path]) == sha(old)})
    write("current_vs_llvm3_elf.tsv", llvm3_rows, list(llvm3_rows[0]))
    section_data = {}
    for image in ("LLVM_current", "GCC"):
        for index, path in enumerate(objects):
            file = pulled[path] if image == "LLVM_current" else MEMDIFF / "data/gcc_baseline/elf/files" / path.lstrip("/")
            if not file.is_file():
                section_data[(image, path)] = None
                continue
            print("readelf", image, path, flush=True)
            section_data[(image, path)] = readelf(file, f"{image}_{index:02d}")
    section_rows = []
    for image in ("LLVM_current", "GCC"):
        for path in objects:
            parsed = section_data[(image, path)]
            if parsed is None:
                continue
            sections, loads = parsed
            rx_size = sum(x["filesz"] for x in loads if "E" in x["flags"])
            for section in sections:
                section_rows.append({"image": image, "object": path, "section": section["name"],
                                     "group": section["group"], "section_type": section["type"],
                                     "file_offset": section["offset"], "size_bytes": section["size"],
                                     "rx_load_filesz_bytes": rx_size})
    write("sections.tsv", section_rows, ["image", "object", "section", "group", "section_type", "file_offset", "size_bytes", "rx_load_filesz_bytes"])
    smaps = {}
    for process, pid in collection["pids"].items():
        name = f"raw/smaps_{process}_{pid}.stdout"
        smaps[process] = smaps_blocks((OUT / name).read_text(errors="replace"))
    mapping_rows = []
    per_section = defaultdict(float)
    total_resident = defaultdict(float)
    total_swapped = defaultdict(float)
    cross_pages = defaultdict(int)
    for m in collection["mappings"]:
        process, path = m["process"], m["path"]
        key = (m["start"], m["end"], m["offset"], m["perms"], path)
        metrics = smaps[process].get(key)
        if metrics is None:
            raise RuntimeError(f"VMA not found in saved smaps: {m['maps_line']}")
        raw = (OUT / m["pagemap_file"]).read_text()
        entries = [int(s, 16) for s in raw.split()]
        if len(entries) != m["pages"]:
            raise RuntimeError(f"page count mismatch: {path} {m['maps_line']}")
        present = [index for index, entry in enumerate(entries) if entry >> 63 & 1]
        swapped = [index for index, entry in enumerate(entries) if entry >> 62 & 1]
        if set(present) & set(swapped):
            raise RuntimeError(f"present/swapped overlap: {path}")
        groupkey = (process, path, m["perms"][:3])
        total_resident[groupkey] += len(present) * page_size / 1024
        total_swapped[groupkey] += len(swapped) * page_size / 1024
        sections = section_data[("LLVM_current", path)][0]
        for page_index in present:
            start = m["offset"] + page_index * page_size
            end = start + page_size
            allocated = 0
            touched = 0
            for section in sections:
                if section["type"] == "NOBITS":
                    continue
                overlap = max(0, min(end, section["offset"] + section["size"]) - max(start, section["offset"]))
                if overlap:
                    per_section[(*groupkey, section["name"], section["group"])] += overlap / 1024
                    allocated += overlap
                    touched += 1
            if allocated > page_size:
                raise RuntimeError(f"overlapping ELF sections > page: {path} offset {start}")
            if allocated < page_size:
                per_section[(*groupkey, "<headers/padding/unassigned>", "other")] += (page_size - allocated) / 1024
            if touched > 1:
                cross_pages[groupkey] += 1
        mapping_rows.append({"process": process, "object": path, "perms": m["perms"],
                             "start_hex": hex(m["start"]), "end_hex": hex(m["end"]),
                             "file_offset_hex": hex(m["offset"]), "pages": m["pages"],
                             "present_pages": len(present), "swapped_pages": len(swapped),
                             "pagemap_Rss_kB": len(present) * page_size // 1024,
                             "smaps_Rss_kB": metrics.get("Rss", "MISSING"),
                             "smaps_Pss_kB": metrics.get("Pss", "MISSING"),
                             "smaps_Private_Dirty_kB": metrics.get("Private_Dirty", "MISSING"),
                             "pagemap_file": m["pagemap_file"]})
    write("mappings.tsv", mapping_rows, list(mapping_rows[0]))
    section_resident_rows = []
    for (process, path, perms, name, section_group), kib in sorted(per_section.items()):
        section_resident_rows.append({"process": process, "object": path, "perms": perms,
                                      "section": name, "group": section_group,
                                      "resident_kB": round(kib, 6),
                                      "cross_section_pages_in_mapping_group": cross_pages[(process, path, perms)]})
    write("section_residency.tsv", section_resident_rows, list(section_resident_rows[0]))
    for key, resident in total_resident.items():
        accounted = sum(v for (p, obj, perms, section, group_name), v in per_section.items()
                        if (p, obj, perms) == key)
        if abs(accounted - resident) > 1e-6:
            raise RuntimeError(f"allocation mismatch: {key} {accounted} != {resident}")
    original = {}
    with (MEMDIFF / "data/tvs_daemon_code_pages/object_summary.tsv").open() as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            original[(row["process"], row["object"])] = row
    summary = []
    group_rows = []
    for process, path in sorted({(m["process"], m["path"]) for m in collection["mappings"]}):
        rx = total_resident[(process, path, "r-x")]
        loader_rx = sum(v for (p, obj, perms, section, grp), v in per_section.items()
                        if (p, obj, perms) == (process, path, "r-x") and grp in LOADER)
        text_rx = sum(v for (p, obj, perms, section, grp), v in per_section.items()
                      if (p, obj, perms) == (process, path, "r-x") and grp == "text")
        gcc = original.get((process, path))
        gcc_mean_rss = float(gcc["GCC_mean_Rss_kB"]) if gcc else None
        gcc_sections = section_data[("GCC", path)]
        gcc_loader_size = sum(s["size"] for s in gcc_sections[0] if s["group"] in LOADER) / 1024 if gcc_sections else None
        summary.append({"process": process, "object": path,
                        "current_rx_Rss_kB": round(rx, 3),
                        "current_rx_loader_resident_kB": round(loader_rx, 6),
                        "current_rx_text_resident_kB": round(text_rx, 6),
                        "current_rx_loader_fraction_pct": round(loader_rx/rx*100, 3) if rx else 0,
                        "current_rx_text_fraction_pct": round(text_rx/rx*100, 3) if rx else 0,
                        "LLVM3_boot1_rx_Rss_kB": gcc["LLVM1_Rss_kB"] if gcc else "MISSING",
                        "LLVM3_boot2_rx_Rss_kB": gcc["LLVM2_Rss_kB"] if gcc else "MISSING",
                        "GCC_boot1_rx_Rss_kB": gcc["GCC1_Rss_kB"] if gcc else "MISSING",
                        "GCC_boot2_rx_Rss_kB": gcc["GCC2_Rss_kB"] if gcc else "MISSING",
                        "GCC_mean_rx_Rss_kB": gcc_mean_rss if gcc_mean_rss is not None else "MISSING",
                        "GCC_loader_sections_size_kB": round(gcc_loader_size, 3) if gcc_loader_size is not None else "MISSING",
                        "GCC_Rss_lt_loader_size": (gcc_mean_rss < gcc_loader_size) if gcc_mean_rss is not None and gcc_loader_size is not None else "UNKNOWN"})
        for grp in GROUPS:
            current_size = sum(s["size"] for s in section_data[("LLVM_current", path)][0] if s["group"] == grp) / 1024
            gcc_size = sum(s["size"] for s in gcc_sections[0] if s["group"] == grp) / 1024 if gcc_sections else None
            resident_by_perm = {perms: sum(v for (p, obj, perm, section, group_name), v in per_section.items()
                                           if (p, obj, perm, group_name) == (process, path, perms, grp))
                                for perms in ("r-x", "r--", "rw-")}
            group_rows.append({"process": process, "object": path, "group": grp,
                               "LLVM_current_size_kB": round(current_size, 6),
                               "GCC_size_kB": round(gcc_size, 6) if gcc_size is not None else "MISSING",
                               **{f"LLVM_current_{perm}_resident_kB": round(value, 6)
                                  for perm, value in resident_by_perm.items()}})
    write("object_summary.tsv", summary, list(summary[0]))
    write("group_summary.tsv", group_rows, list(group_rows[0]))
    wide = []
    grouped = defaultdict(dict)
    for row in group_rows:
        grouped[(row["process"], row["object"])][row["group"]] = row
    for (process, path), groups in sorted(grouped.items()):
        row = {"process": process, "object": path}
        for grp in GROUPS:
            source = groups[grp]
            row[f"{grp}_size_kB"] = source["LLVM_current_size_kB"]
            row[f"{grp}_resident_rx_kB"] = source["LLVM_current_r-x_resident_kB"]
            row[f"{grp}_resident_all_file_mappings_kB"] = round(sum(source[f"LLVM_current_{perm}_resident_kB"] for perm in ("r-x", "r--", "rw-")), 6)
        wide.append(row)
    write("object_sections_wide.tsv", wide, list(wide[0]))
    print("DONE", len(mapping_rows), "VMAs", len(summary), "objects", flush=True)


if __name__ == "__main__":
    main()
