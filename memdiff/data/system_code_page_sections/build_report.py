#!/usr/bin/env python3
"""Render system-wide page/ELF evidence and export dynamic comparison tables."""
import csv
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parents[1] / "reports/system_code_page_sections.md"
PRIOR = HERE.parents[1] / "data/code_page_sections/object_summary.tsv"


def read(name):
    with (HERE / name).open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write(name, rows, fields):
    with (HERE / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def table(lines, headers, rows):
    lines.extend(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"])
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    lines.append("")


def num(value):
    return f"{float(value):,.1f}"


def main():
    state = json.loads((HERE / "collection.json").read_text())
    if state.get("status") != "DONE" or not state.get("root_restored") or not state.get("boot_id_unchanged"):
        raise RuntimeError("board identity/restoration gate failed")
    files = read("file_residency.tsv")
    vmas = read("vmas.tsv")
    smaps_discrepancies = sum(abs(int(v["present_pages"])*state["page_size"]//1024-int(v["Rss_kB"])) > 0
                              for v in vmas if v["Rss_kB"] not in ("", None))
    summary = read("summary.tsv")
    top20 = read("nonloader_gt_GCC_top20.tsv")
    elf = read("elf_summary.tsv")
    weekly = json.loads((HERE / "weekly_reconciliation.json").read_text())
    analysis = json.loads((HERE / "elf_analysis_summary.json").read_text())
    by_side = {side: {r["path"]: r for r in elf if r["image"] == side} for side in ("GCC", "LLVM")}
    common = sorted(set(by_side["GCC"]) & set(by_side["LLVM"]))
    metric_names = ("defined_GLOBAL", "defined_WEAK", "undefined", ".dynstr_bytes", ".dynsym_bytes", ".rel.plt_bytes", ".plt_bytes")
    pairs = []
    for path in common:
        gcc, llvm = by_side["GCC"][path], by_side["LLVM"][path]
        row = {"path": path}
        for metric in metric_names:
            g = int(gcc[metric]); l = int(llvm[metric])
            row[f"GCC_{metric}"] = g; row[f"LLVM_{metric}"] = l; row[f"LLVM_minus_GCC_{metric}"] = l-g
        pairs.append(row)
    write("paired_dynamic.tsv", pairs, list(pairs[0]))
    prior_paths = []
    with PRIOR.open() as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            prior_paths.append(row["object"])
    prior_paths = sorted(set(prior_paths))
    if len(prior_paths) != 13:
        raise RuntimeError(f"prior object set has {len(prior_paths)} paths, expected 13")
    thirteen = [r for r in pairs if r["path"] in prior_paths]
    write("thirteen_dynamic.tsv", thirteen, list(pairs[0]))
    exceptions = []
    for side in ("GCC", "LLVM"):
        for path, row in by_side[side].items():
            if (side == "GCC" and row["prelink_marker_any"] != "True") or (side == "LLVM" and row["prelink_marker_any"] == "True"):
                exceptions.append({"image": side, "path": path,
                                   "reason": "GCC_unmarked" if side == "GCC" else "LLVM_marked"})
    write("prelink_marker_exceptions.tsv", exceptions, ["image", "path", "reason"])
    categories = defaultdict(Counter)
    with gzip.open(HERE / "llvm_extra_exported_symbols.tsv.gz", "rt") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            categories[row["path"]][row["category"]] += 1
    cat_names = ("vtable_typeinfo", "template_instance_candidate", "class_member_inline_unverified",
                 "class_member_inline_undetermined", "other")
    category_rows = [{"path": path, **{cat: categories[path][cat] for cat in cat_names},
                      "total_extra_defined_exports": sum(categories[path].values())} for path in common]
    write("symbol_category_counts.tsv", category_rows, list(category_rows[0]))

    process_counter = Counter(p["status"] for p in state["processes"])
    pull_counter = Counter(p["status"] for p in state["pulled"])
    exclusions = Counter(r["exclude_reasons"] for r in files if r["population"] == "common" and r["eligible"] != "True")
    excluded_common = [r for r in files if r["population"] == "common" and r["eligible"] != "True"]
    marker_counts = {side: (sum(row["prelink_marker_any"] == "True" for row in by_side[side].values()), len(by_side[side])) for side in ("GCC", "LLVM")}
    rel_types = {side: Counter(row["rel_dyn_section_type"] for row in by_side[side].values()) for side in ("GCC", "LLVM")}
    rows = []
    for r in summary:
        rows.append((r["population"], r["files"], num(r["LLVM_unique_rx_Rss_kB"]),
                     f"{num(r['GCC1_rx_Pss_sum_kB'])} / {num(r['GCC2_rx_Pss_sum_kB'])}",
                     num(r["GCC_mean_rx_Pss_sum_kB"]), num(r["LLVM_minus_GCC_mean_kB"]),
                     num(r["LLVM_loader_resident_kB"]), num(r["loader_growth_strict_lower_kB"]),
                     f"{r['nonloader_le_GCC_files']} / {r['nonloader_gt_GCC_files']}"))
    lines = ["# VD LLVM 全系统 r-x 驻留页 ELF 节归属及 GCC 对照", "",
             "## 采集范围与质量", "",
             f"板子 `{state['ip']}`；BUILD_ID `{state['build_id']}` 与上一轮一致；armv7l、NT72671D、KSU2E、clang 内核四项均通过。初始 PID {state['pid_count_initial']} 个，完整采集 {process_counter['complete']} 个，退出或不完整 {process_counter['exited_or_incomplete']} 个；不重试。唯一映射路径 {len(state['mapped_paths'])} 个，拉回且 SHA256 一致 {pull_counter['hash_match']} 个、失败 {pull_counter['pull_failed']} 个，其中 ELF {sum(p.get('is_elf', False) for p in state['pulled'])} 个。`sdb root off` 后 UID 恢复、boot ID 未变。每个 PID 只开一个 SDB shell 会话，逐 r-xp 文件 VMA 执行一次 `dd /proc/PID/pagemap | od`；原始 maps/smaps/pagemap、命令及返回码见 [`collection.json`](../data/system_code_page_sections/collection.json) 与 `raw/`。", "",
             f"解析出 {len(vmas)} 个 r-xp 文件 VMA，pagemap present×页大小与同 VMA smaps Rss 不一致的有 {smaps_discrepancies} 个。进程状态和失败列表见 [`process_parse_errors.tsv`](../data/system_code_page_sections/process_parse_errors.tsv)，ELF 拉取失败/非 ELF/哈希状态见 `collection.json`。开发机 CPU0、nice19、串行、Python 虚拟内存上限 2.5 GB。采集前后未在板上写文件、未重启。", "",
             "## 逐页算法与文件集合", "",
             "沿用上一轮 [`analyze.py`](../data/code_page_sections/analyze.py) 的节归属规则：每个 present 页按映射文件偏移与 `readelf -SW` 的节区间相交；跨节页按交集字节数分摊，不属于节的字节计入“其余”。加载器相关节仅 `.dynsym/.dynstr/.gnu.hash/.hash/.gnu.version*/.rel.dyn/.rel.plt`；`.plt` 不并入。逐 PID 原始数据经 [`parse_pages.py`](../data/system_code_page_sections/parse_pages.py) 转为 [`vmas.tsv`](../data/system_code_page_sections/vmas.tsv)、[`unique_pages.tsv.gz`](../data/system_code_page_sections/unique_pages.tsv.gz)；逐节驻留见 [`section_residency.tsv`](../data/system_code_page_sections/section_residency.tsv)，完整逐文件表见 [`file_residency.tsv`](../data/system_code_page_sections/file_residency.tsv)。", "",
             "对同一路径的所有 present r-xp 页以文件偏移取并集；遇到 r-x Private_Dirty、DT_TEXTREL、同路径多个 dev/inode、同 inode 多路径别名或已删除映射，文件单列且不参与可信总量。GCC 采用两次 `02_steady/smaps_raw.txt.gz` 中该路径全部 r-xp VMA 的 Pss 之和；Pss 逐映射舍入使它只近似文件唯一驻留量。两边文件路径取交集，且当前文件必须是哈希一致、可解析的 ELF，才进入下表；GCC 静态节缺失或读取错误亦排除。" + f"全路径共 {len(files)}，两侧都出现 {sum(r['population']=='common' for r in files)}，可信共同文件 {summary[0]['files']}；" + "单侧文件见 [`single_side_files.tsv`](../data/system_code_page_sections/single_side_files.tsv)。共同文件的排除原因统计：" + "；".join(f"{reason}={count}" for reason, count in sorted(exclusions.items())) + "。同 inode 别名见 [`inode_path_aliases.tsv`](../data/system_code_page_sections/inode_path_aliases.tsv)。", "",
             f"被排除的共同文件 {len(excluded_common)} 个，原始偏移并集读数合计 {num(sum(float(r['LLVM_unique_rx_Rss_kB'] or 0) for r in excluded_common))} KiB、GCC Pss 均值 {num(sum(float(r['GCC_mean_rx_Pss_sum_kB'] or 0) for r in excluded_common))} KiB；因非 ELF、缺副本或不可可靠去重，不能加入下面的 ELF 节归属汇总。", "",
             "## 第一部分：全系统与 prelink.conf 子集", ""]
    table(lines, ["集合", "文件数", "LLVM 唯一 r-x KiB", "GCC1 / GCC2 r-x Pss 和 KiB", "GCC 均值 KiB", "LLVM−GCC KiB", "LLVM 加载器节 KiB", "加载器净增严格下界 KiB", "去加载器后 ≤ GCC / > GCC 文件数"], rows)
    lines.extend(["`prelink.conf` 内以板上原文的 8 条 `-l` 目录为准，见 [`prelink_dirs.json`](../data/system_code_page_sections/prelink_dirs.json)。加载器节净增下界逐文件计算为 `LLVM 已驻留加载器节 − min(GCC 两次平均 r-x Pss 和, GCC 板上副本加载器节静态大小)`，可为负；汇总为这些逐文件下界之和。GCC 副本已被出镜像 prelink 处理，且 Pss 有舍入，因此“严格”指按该证据口径的数学上界，不是同镜像干预实验的收益。", "",
                  "去加载器节后仍大于 GCC 的文件，差值最大的前 20 个："])
    table(lines, ["文件", "LLVM 去加载器节后 − GCC KiB", "LLVM 唯一 r-x KiB", "GCC 均值 KiB"],
          [(f"`{r['path']}`", num(r["LLVM_nonloader_minus_GCC_kB"]), num(r["LLVM_unique_rx_Rss_kB"]),
            num(r["GCC_mean_rx_Pss_sum_kB"])) for r in top20])
    lines.extend(["完整逐文件判断在 `file_residency.tsv`；以上差值可能受不同 BUILD_ID、进程集合和工作负载影响，不把它归因于编译器。", "",
                  "### 与周报 `+5.2 MiB` 对账", "",
                  f"[`weekly_data_table.md`](../reports/weekly_data_table.md) 第 149–160 行的 +5.168457 MiB = +{num(weekly['LLVM3_minus_GCC_kB'])} KiB，来源 [`clang_matched_paths_summary.tsv`](../data/llvm_round3/analysis/clang_matched_paths_summary.tsv) 的 `matched_all_four/code_r-x/Pss`：{weekly['paths_in_historical_set']} 个四次都匹配、第三轮 LLVM `.comment` 含 clang 的路径，逐映射 smaps Pss 求和；GCC/LLVM3 两次均值为 {num(weekly['GCC_historical_mean_kB'])}/{num(weekly['LLVM3_historical_mean_kB'])} KiB。它不是全系统文件偏移去重的 Rss。", "",
                  f"本次按相同的历史路径集合和逐映射 Pss 口径重算当前板：{weekly['paths_present_current']} 个路径仍在、{weekly['paths_absent_current']} 个缺席，Pss 和 {num(weekly['current_per_mapping_rx_Pss_sum_kB'])} KiB；相对同一 GCC 历史均值为 +{num(weekly['current_minus_GCC_historical_kB'])} KiB。此数可对账口径，但当前板 BUILD_ID 比第三轮新、运行进程集合不同、采集时刻不同，不能解释为编译器收益。文件路径集合与口径明细见 [`weekly_reconciliation.json`](../data/system_code_page_sections/weekly_reconciliation.json)。", "",
                  "## 第二部分：预链接标记与 .rel.dyn 类型", ""])
    table(lines, ["镜像副本", "带任一预链接标记 / 全 ELF", ".rel.dyn REL / RELA / 缺失"],
          [(side, f"{marker_counts[side][0]} / {marker_counts[side][1]}",
            f"{rel_types[side]['REL']} / {rel_types[side]['RELA']} / {rel_types[side]['MISSING']}") for side in ("GCC", "LLVM")])
    marker_fields = (".gnu.prelink_undo", ".gnu.liblist", ".gnu.conflict", "GNU_PRELINKED", "GNU_LIBLIST", "CHECKSUM")
    table(lines, ["镜像副本", *marker_fields],
          [(side, *[str(sum(r[field] == "True" for r in by_side[side].values())) for field in marker_fields])
           for side in ("GCC", "LLVM")])
    lines.extend(["标记指 `.gnu.prelink_undo/.gnu.liblist/.gnu.conflict` 节或动态段 `GNU_PRELINKED/GNU_LIBLIST/CHECKSUM` 任一项。每个 ELF 的六项布尔值、`.rel.dyn` 类型和 readelf 返回码见 [`elf_summary.tsv`](../data/system_code_page_sections/elf_summary.tsv)。GCC 无标记与 LLVM 有标记的例外全表见 [`prelink_marker_exceptions.tsv`](../data/system_code_page_sections/prelink_marker_exceptions.tsv)；readelf 错误原文见 [`readelf_errors.tsv`](../data/system_code_page_sections/readelf_errors.tsv)。只记录标记，不由标记推断加载器运行时是否采用预链接。", "",
                  "## 第三部分：动态表与额外导出符号", "",
                  f"两侧都有 ELF 副本的路径 {len(common)} 个。逐 ELF 的已定义 GLOBAL/WEAK、未定义符号和 `.dynstr/.dynsym/.rel.plt/.plt` 大小见 [`paired_dynamic.tsv`](../data/system_code_page_sections/paired_dynamic.tsv)，原始 `.dynsym` 条目在 [`dynsym_symbols.tsv.gz`](../data/system_code_page_sections/dynsym_symbols.tsv.gz)。额外导出符号按名称精确集合差比较（DEFAULT/PROTECTED 可见且已定义），再用 GBS root 交叉 `c++filt` 反解，逐符号见 [`llvm_extra_exported_symbols.tsv.gz`](../data/system_code_page_sections/llvm_extra_exported_symbols.tsv.gz)。", "",
                  "### 上一轮 13 个对象", ""])
    thirteen_by = {r["path"]: r for r in thirteen}
    display = []
    for path in prior_paths:
        r = thirteen_by.get(path)
        if not r:
            display.append((f"`{path}`", "缺副本", "", "", "", "")); continue
        counts = categories[path]
        display.append((f"`{path}`", f"{r['GCC_defined_WEAK']} / {r['LLVM_defined_WEAK']}",
                        f"{r['GCC_defined_GLOBAL']} / {r['LLVM_defined_GLOBAL']}",
                        f"{r['GCC_undefined']} / {r['LLVM_undefined']}",
                        " / ".join(f"{int(r['GCC_'+n])/1024:.1f}→{int(r['LLVM_'+n])/1024:.1f}" for n in (".dynstr_bytes", ".dynsym_bytes", ".rel.plt_bytes", ".plt_bytes")),
                        str(sum(counts.values()))))
    table(lines, ["对象", "已定义 WEAK GCC/LLVM", "已定义 GLOBAL GCC/LLVM", "未定义 GCC/LLVM", ".dynstr/.dynsym/.rel.plt/.plt GCC→LLVM KiB", "LLVM 额外导出名数"], display)
    lines.extend(["13 对象的独立 TSV：[`thirteen_dynamic.tsv`](../data/system_code_page_sections/thirteen_dynamic.tsv)。", "",
                  "### 全部共同 ELF 合计", ""])
    total_rows = []
    for metric in metric_names:
        g = sum(int(r["GCC_" + metric]) for r in pairs)
        l = sum(int(r["LLVM_" + metric]) for r in pairs)
        unit = "个" if metric in ("defined_GLOBAL", "defined_WEAK", "undefined") else "字节"
        total_rows.append((metric, f"{g:,}", f"{l:,}", f"{l-g:+,}", unit))
    table(lines, ["指标", "GCC", "LLVM", "LLVM−GCC", "单位"], total_rows)
    all_categories = Counter()
    for counts in categories.values():
        all_categories.update(counts)
    table(lines, ["LLVM 额外已定义导出名类别", "数量", "判定"],
          [(cat, f"{all_categories[cat]:,}",
            "名称反解可识别" if cat == "vtable_typeinfo" else
            "按 <...> 名称模式，候选" if cat == "template_instance_candidate" else
            "仅可确认是类成员函数；是否类内定义/inline 未确定" if cat.startswith("class_member") else
            "其他/未确定") for cat in cat_names])
    lines.extend([f"额外导出名共 {sum(all_categories.values()):,} 个；逐文件类别计数见 [`symbol_category_counts.tsv`](../data/system_code_page_sections/symbol_category_counts.tsv)。`c++filt` 只能给出名字，不能证明类成员函数是否在类内定义或是否 inline；这两类在报告中明确记为未确定，不作修改建议。符号版本后缀按 readelf 原样名称比较；版本差可能被计为额外名。构建根工具与 `LD_LIBRARY_PATH` 在 [`readelf_tool.txt`](../data/system_code_page_sections/readelf_tool.txt)。", ""])
    REPORT.write_text("\n".join(lines) + "\n")
    print("report", REPORT, "common eligible", summary[0]["files"], "paired ELF", len(pairs), flush=True)


if __name__ == "__main__":
    main()
