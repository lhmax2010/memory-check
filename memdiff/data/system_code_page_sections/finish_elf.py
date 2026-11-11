#!/usr/bin/env python3
"""Resume only C++ symbol demangling from completed readelf TSV output."""
import csv
import gzip
import json
import os
import subprocess
from collections import defaultdict

import analyze_elf as base


def main():
    exports = {"GCC": defaultdict(dict), "LLVM": defaultdict(dict)}
    with gzip.open(base.HERE / "dynsym_symbols.tsv.gz", "rt") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["ndx"] != "UND" and row["bind"] in ("GLOBAL", "WEAK") and row["visibility"] in ("DEFAULT", "PROTECTED") and row["name"]:
                exports[row["image"]][row["path"]][row["name"]] = row["bind"]
    with (base.HERE / "elf_summary.tsv").open() as stream:
        summary_rows = list(csv.DictReader(stream, delimiter="\t"))
    gcc_paths = {r["path"] for r in summary_rows if r["image"] == "GCC"}
    llvm_paths = {r["path"] for r in summary_rows if r["image"] == "LLVM"}
    common = sorted(gcc_paths & llvm_paths)
    extra = []
    for path in common:
        for symbol in sorted(exports["LLVM"][path].keys() - exports["GCC"][path].keys()):
            extra.append({"path": path, "symbol": symbol, "LLVM_bind": exports["LLVM"][path][symbol]})
    names = sorted({row["symbol"] for row in extra})
    decoded = {}
    for start in range(0, len(names), 5000):
        chunk = names[start:start + 5000]
        result = subprocess.run([str(base.FILT)], input="\n".join(chunk) + "\n", text=True,
                                capture_output=True, timeout=120,
                                env={**os.environ, "LD_LIBRARY_PATH": str(base.FILT_LIB)})
        if result.returncode:
            raise RuntimeError(f"cross c++filt rc={result.returncode}: {result.stderr}")
        lines = result.stdout.splitlines()
        if len(lines) != len(chunk):
            raise RuntimeError(f"c++filt lines {len(lines)} != input {len(chunk)}")
        decoded.update(zip(chunk, lines))
        print("demangled", min(start+5000, len(names)), "/", len(names), flush=True)
    for row in extra:
        demangled = decoded[row["symbol"]]
        row["demangled"] = demangled
        row["category"] = base.category(demangled, row["symbol"], row["LLVM_bind"])
    with gzip.open(base.HERE / "llvm_extra_exported_symbols.tsv.gz", "wt") as stream:
        writer = csv.DictWriter(stream, ["path", "symbol", "LLVM_bind", "demangled", "category"], delimiter="\t", lineterminator="\n")
        writer.writeheader(); writer.writerows(extra)
    with (base.HERE / "readelf_errors.tsv").open() as stream:
        errors = list(csv.DictReader(stream, delimiter="\t"))
    summary = {"GCC_ELF_count": len(gcc_paths), "LLVM_ELF_count": len(llvm_paths),
               "common_paths": len(common), "extra_exported_symbols": len(extra),
               "readelf_errors": len(errors), "readelf": str(base.READELF),
               "cxxfilt": str(base.FILT), "cxxfilt_LD_LIBRARY_PATH": str(base.FILT_LIB)}
    (base.HERE / "elf_analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print("已结束 GCC", len(gcc_paths), "LLVM", len(llvm_paths), "common", len(common), flush=True)


if __name__ == "__main__":
    main()
