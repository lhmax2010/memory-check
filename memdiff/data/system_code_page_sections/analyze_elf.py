#!/usr/bin/env python3
"""Offline cross-readelf inventory of all saved GCC and freshly pulled LLVM ELF files."""
import csv
import gzip
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEMDIFF = HERE.parents[1]
GCC_ROOT = MEMDIFF / "data/gcc_baseline/elf/files"
TOOL_ROOT = Path("/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin")
READELF = TOOL_ROOT / "armv7l-tizen-linux-gnueabi-readelf"
FILT = TOOL_ROOT / "armv7l-tizen-linux-gnueabi-c++filt"
FILT_LIB = TOOL_ROOT.parent / "lib64"
SECTION = re.compile(r"^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s")
PRELINK_SECTIONS = (".gnu.prelink_undo", ".gnu.liblist", ".gnu.conflict")
PRELINK_TAGS = ("GNU_PRELINKED", "GNU_LIBLIST", "CHECKSUM")
spec = importlib.util.spec_from_file_location("prior_sections", MEMDIFF / "data/code_page_sections/analyze.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


def tsv(name, rows, fields):
    with (HERE / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def readelf(path, flags):
    result = subprocess.run([str(READELF), *flags, str(path)], stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, errors="replace", timeout=120)
    return result.returncode, result.stdout, result.stderr


def sections_from(text):
    rows = []
    for line in text.splitlines():
        match = SECTION.match(line)
        if match:
            name, kind, _, offset, size = match.groups()
            rows.append({"section": name, "section_type": kind, "file_offset": int(offset, 16),
                         "size_bytes": int(size, 16), "group": prior.group(name)})
    return rows


def dynamic_symbols(text):
    symbols = []
    in_dynsym = False
    for line in text.splitlines():
        if line.startswith("Symbol table '"):
            in_dynsym = line.startswith("Symbol table '.dynsym'")
            continue
        if not in_dynsym:
            continue
        parts = line.split()
        if len(parts) < 8 or not parts[0].endswith(":") or not parts[0][:-1].isdigit():
            continue
        symbols.append({"bind": parts[4], "visibility": parts[5],
                        "ndx": parts[6], "name": parts[7]})
    return symbols


def elf_files(root):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            if stream.read(4) == b"\x7fELF":
                yield path


def category(demangled, raw, bind):
    if demangled.startswith(("vtable for ", "typeinfo for ", "typeinfo name for ", "VTT for ")) or raw.startswith(("_ZTV", "_ZTI", "_ZTS", "_ZTT")):
        return "vtable_typeinfo"
    if "<" in demangled and ">" in demangled:
        return "template_instance_candidate"
    if "::" in demangled and "(" in demangled:
        return "class_member_inline_unverified" if bind == "WEAK" else "class_member_inline_undetermined"
    return "other"


def main():
    collection = json.loads((HERE / "collection.json").read_text())
    if collection.get("status") != "DONE" or not collection.get("root_restored"):
        raise RuntimeError("collection incomplete")
    good_llvm = {item["path"]: HERE / item["local"] for item in collection["pulled"]
                 if item.get("status") == "hash_match" and item.get("is_elf")}
    gcc_files = {"/" + str(path.relative_to(GCC_ROOT)): path for path in elf_files(GCC_ROOT)}
    inventories = (("GCC", gcc_files), ("LLVM", good_llvm))
    section_rows, summary_rows, error_rows = [], [], []
    exports = {"GCC": {}, "LLVM": {}}
    symbol_stream = gzip.open(HERE / "dynsym_symbols.tsv.gz", "wt")
    symbol_writer = csv.DictWriter(symbol_stream, ["image", "path", "bind", "visibility", "ndx", "name"], delimiter="\t", lineterminator="\n")
    symbol_writer.writeheader()
    ver = subprocess.run([str(READELF), "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True)
    (HERE / "readelf_tool.txt").write_text(str(READELF) + "\n" + ver.stdout + ver.stderr + "\n" + str(FILT) + "\nLD_LIBRARY_PATH=" + str(FILT_LIB) + "\n")
    for image, files in inventories:
        for index, (path, file) in enumerate(sorted(files.items()), 1):
            results = {}
            for key, flags in (("sections", ["-SW"]), ("dynamic", ["-dW"]), ("dynsym", ["--dyn-syms", "-W"])):
                try:
                    rc, stdout, stderr = readelf(file, flags)
                except subprocess.TimeoutExpired:
                    rc, stdout, stderr = 124, "", "timeout"
                if rc:
                    error_rows.append({"image": image, "path": path, "operation": key, "rc": rc, "stderr": stderr.strip()})
                results[key] = (rc, stdout, stderr)
            secs = sections_from(results["sections"][1])
            if not secs:
                error_rows.append({"image": image, "path": path, "operation": "parse_sections", "rc": -1, "stderr": "no sections"})
            for sec in secs:
                section_rows.append({"image": image, "path": path, **sec})
            byname = {sec["section"]: sec for sec in secs}
            dyn = results["dynamic"][1]
            symbols = dynamic_symbols(results["dynsym"][1])
            counts = {"defined_GLOBAL": 0, "defined_WEAK": 0, "undefined": 0}
            exported = {}
            for sym in symbols:
                if sym["ndx"] == "UND":
                    counts["undefined"] += 1
                elif sym["bind"] in ("GLOBAL", "WEAK"):
                    counts["defined_" + sym["bind"]] += 1
                    if sym["visibility"] in ("DEFAULT", "PROTECTED") and sym["name"]:
                        exported[sym["name"]] = sym["bind"]
                symbol_writer.writerow({"image": image, "path": path, **sym})
            exports[image][path] = exported
            marker = any(key in byname for key in PRELINK_SECTIONS) or any(tag in dyn for tag in PRELINK_TAGS)
            rel_dyn = byname.get(".rel.dyn") or byname.get(".rela.dyn")
            summary_rows.append({"image": image, "path": path,
                                 **{name: name in byname for name in PRELINK_SECTIONS},
                                 **{tag: tag in dyn for tag in PRELINK_TAGS},
                                 "prelink_marker_any": marker,
                                 "rel_dyn_section_type": rel_dyn["section_type"] if rel_dyn else "MISSING",
                                 "DT_TEXTREL": "TEXTREL" in dyn,
                                 **counts,
                                 **{name + "_bytes": byname.get(name, {}).get("size_bytes", 0)
                                    for name in (".dynsym", ".dynstr", ".rel.plt", ".plt")},
                                 "ELF_size_bytes": file.stat().st_size,
                                 "section_readelf_rc": results["sections"][0],
                                 "dynamic_readelf_rc": results["dynamic"][0],
                                 "dynsym_readelf_rc": results["dynsym"][0]})
            if index % 50 == 0:
                print(image, index, "/", len(files), "readelf complete", flush=True)
    tsv("elf_sections.tsv", section_rows, list(section_rows[0]))
    tsv("elf_summary.tsv", summary_rows, list(summary_rows[0]))
    tsv("readelf_errors.tsv", error_rows, ["image", "path", "operation", "rc", "stderr"])
    symbol_stream.close()
    common = sorted(exports["GCC"].keys() & exports["LLVM"].keys())
    extra = []
    for path in common:
        for symbol in sorted(exports["LLVM"][path].keys() - exports["GCC"][path].keys()):
            extra.append({"path": path, "symbol": symbol, "LLVM_bind": exports["LLVM"][path][symbol]})
    names = sorted({row["symbol"] for row in extra})
    decoded = {}
    for start in range(0, len(names), 5000):
        chunk = names[start:start + 5000]
        result = subprocess.run([str(FILT)], input="\n".join(chunk) + "\n", text=True,
                                capture_output=True, timeout=120,
                                env={**os.environ, "LD_LIBRARY_PATH": str(FILT_LIB)})
        if result.returncode:
            raise RuntimeError(f"cross c++filt rc={result.returncode}: {result.stderr}")
        outputs = result.stdout.splitlines()
        if len(outputs) != len(chunk):
            raise RuntimeError("cross c++filt line count mismatch")
        decoded.update(zip(chunk, outputs))
    for row in extra:
        demangled = decoded[row["symbol"]]
        row["demangled"] = demangled
        row["category"] = category(demangled, row["symbol"], row["LLVM_bind"])
    with gzip.open(HERE / "llvm_extra_exported_symbols.tsv.gz", "wt") as stream:
        writer = csv.DictWriter(stream, ["path", "symbol", "LLVM_bind", "demangled", "category"], delimiter="\t", lineterminator="\n")
        writer.writeheader(); writer.writerows(extra)
    summary = {"GCC_ELF_count": len(gcc_files), "LLVM_ELF_count": len(good_llvm),
               "common_paths": len(common), "extra_exported_symbols": len(extra),
               "readelf_errors": len(error_rows), "readelf": str(READELF), "cxxfilt": str(FILT)}
    (HERE / "elf_analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("已结束", len(gcc_files), "GCC", len(good_llvm), "LLVM", len(common), "common", flush=True)


if __name__ == "__main__":
    main()
