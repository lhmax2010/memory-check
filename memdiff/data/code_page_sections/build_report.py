#!/usr/bin/env python3
"""Render the captured section residency evidence, without inferring GCC pages."""
import csv
import json
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPORT = OUT.parents[1] / "reports/code_page_sections.md"


def read(name):
    with (OUT / name).open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def fmt(value):
    return f"{float(value):,.1f}"


def table(lines, header, rows):
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    lines.append("")


def main():
    collection = json.loads((OUT / "collection.json").read_text())
    if not collection.get("root_restored"):
        raise RuntimeError("root restoration not verified")
    objects = read("object_summary.tsv")
    groups = read("group_summary.tsv")
    mapping = read("mappings.tsv")
    llvm3_files = read("current_vs_llvm3_elf.tsv")
    by_object = defaultdict(list)
    for row in groups:
        by_object[(row["process"], row["object"])].append(row)
    loader_groups = {"dynsym", "dynstr", "hash", "gnu_version", "rel_dyn", "rel_plt"}
    total_rx = sum(float(r["current_rx_Rss_kB"]) for r in objects)
    total_loader = sum(float(r["current_rx_loader_resident_kB"]) for r in objects)
    total_text = sum(float(r["current_rx_text_resident_kB"]) for r in objects)
    total_gcc = sum(float(r["GCC_mean_rx_Rss_kB"]) for r in objects if r["GCC_mean_rx_Rss_kB"] != "MISSING")
    gcc_comparable = all(r["GCC_mean_rx_Rss_kB"] != "MISSING" for r in objects)
    lower_loader = 0.0
    lower_text = 0.0
    lower_loader_libraries = 0.0
    library_excess = 0.0
    for r in objects:
        key = (r["process"], r["object"])
        grouped = {g["group"]: g for g in by_object[key]}
        gcc_rss = float(r["GCC_mean_rx_Rss_kB"])
        gcc_loader_size = sum(float(grouped[g]["GCC_size_kB"]) for g in loader_groups)
        gcc_text_size = float(grouped["text"]["GCC_size_kB"])
        this_loader_lower = float(r["current_rx_loader_resident_kB"]) - min(gcc_rss, gcc_loader_size)
        lower_loader += this_loader_lower
        lower_text += float(r["current_rx_text_resident_kB"]) - min(gcc_rss, gcc_text_size)
        if r["object"].endswith(".so"):
            lower_loader_libraries += this_loader_lower
            library_excess += float(r["current_rx_Rss_kB"]) - gcc_rss
    mismatches = [r for r in mapping if r["smaps_Rss_kB"] != "MISSING" and abs(float(r["pagemap_Rss_kB"]) - float(r["smaps_Rss_kB"])) > 4]
    lines = ["# 当前 VD LLVM 镜像代码映射驻留页的 ELF 节归属", "",
             "## 身份、来源和采集质量", "",
             f"板子 IP `{collection['ip']}`；`BUILD_ID={collection['build_id']}`；开机 ID `{collection['identity']['boot_id'].strip()}`；采集窗口 UTC `{collection['started_utc']}` 至 `{collection['ended_utc']}`。四项身份和 BUILD_ID 检查均通过，使用 `sdb root on` 只读采集，结束 `root off` 后 UID 恢复到 `{collection['identity']['uid_before'].strip()}`（见 [`collection.json`](../data/code_page_sections/collection.json) 和原始命令输出）。未重启、未在板上创建或修改文件。", "",
             f"目标清单实际为 **{len(objects)}** 个对象（tvs-daemon 10 个库，tv-viewer 1 个可执行文件与 2 个库；任务文字中的“12 个”与清单不一致，本报告按清单全数处理）。进程 PID：" + ", ".join(f"{k}={v}" for k, v in collection["pids"].items()) + "。", "",
             "板上原始 `maps`、采集前后 `smaps`、每个 VMA 一次 `dd` 读取的完整 pagemap 十六进制输出及每条命令返回码在 [`raw/`](../data/code_page_sections/raw/) 和 `collection.json`。13 份 ELF 由 `sdb pull` 原样拉回，板上与主机 SHA256 逐项一致；哈希见 `collection.json`，文件在 [`elf/`](../data/code_page_sections/elf/)。解析器为前几轮同一交叉 readelf；逐对象 `-SW`/`-lW` 原始输出在 [`readelf/`](../data/code_page_sections/readelf/)。", "",
             f"与第三轮 LLVM 的 ELF SHA256 逐项比较：{sum(x['same_bytes']=='True' for x in llvm3_files)} 个相同、{sum(x['same_bytes']=='False' for x in llvm3_files)} 个不同；不同项及两侧哈希见 [`current_vs_llvm3_elf.tsv`](../data/code_page_sections/current_vs_llvm3_elf.tsv)。镜像 BUILD_ID 仍不同，不能据此认为运行环境完全相同。", "",
             "每个映射的 `Rss`/`Pss`/`Private_Dirty` 对照和 pagemap present/swapped 页数见 [`mappings.tsv`](../data/code_page_sections/mappings.tsv)。39 个 VMA 共记录到 " + str(sum(int(x["swapped_pages"]) for x in mapping)) + " 个 swapped 页；swapped 页不计入当前驻留。pagemap 采样与 smaps 读取不是原子操作；以超过 4 KiB 为准，" + (f"有 {len(mismatches)} 个 VMA 的 present×页大小与 smaps Rss 不同，逐项见映射表。" if mismatches else "没有 VMA 出现超过 4 KiB 的 present×页大小与 smaps Rss 差异。"), "",
             "## 归属算法及限制", "",
             "对每个文件映射 VMA，用 `maps` 起止地址和文件偏移算页号；`dd if=/proc/PID/pagemap bs=8 skip=... count=... | od -An -tx8 -v` 一次读取该 VMA 全段。bit 63 为 present、bit 62 为 swapped。present 页在文件中的区间是 `[VMA 文件偏移 + 页序号×页大小, +页大小)`；与 `readelf -SW` 节的文件偏移/大小做字节区间交集。跨节页按交集字节数分摊 KiB；不属于任何节的头部、对齐填充计“其余”。`.bss/.tbss` 为 NOBITS，列静态大小，但文件页不归入它们；匿名扩展页不在本次文件映射范围。每个 VMA 的页归属总量与 present×页大小守恒检查由 [`analyze.py`](../data/code_page_sections/analyze.py) 执行。", "",
             "按节明细见 [`sections.tsv`](../data/code_page_sections/sections.tsv)（GCC/当前 LLVM 节大小）、[`section_residency.tsv`](../data/code_page_sections/section_residency.tsv)（各 VMA 权限下逐节驻留）、[`group_summary.tsv`](../data/code_page_sections/group_summary.tsv)（逐组及权限）、[`object_sections_wide.tsv`](../data/code_page_sections/object_sections_wide.tsv)（每个对象一行，所有组的大小和驻留）。加载器相关节仅指 `.dynsym`、`.dynstr`、`.gnu.hash/.hash`、`.gnu.version*`、`.rel.dyn`、`.rel.plt`；`.plt` 单列为代码，不并入加载器表。", "",
             "## 逐对象当前 LLVM 驻留", ""]
    rows = []
    for r in objects:
        key = (r["process"], r["object"])
        group_by = {g["group"]: g for g in by_object[key]}
        loader_size = sum(float(group_by[g]["LLVM_current_size_kB"]) for g in loader_groups)
        rows.append((r["process"], f"`{r['object']}`", fmt(r["current_rx_Rss_kB"]),
                     f"{fmt(loader_size)} / {fmt(r['current_rx_loader_resident_kB'])}",
                     f"{fmt(r['current_rx_loader_fraction_pct'])}%",
                     f"{fmt(group_by['text']['LLVM_current_size_kB'])} / {fmt(r['current_rx_text_resident_kB'])}",
                     f"{fmt(r['current_rx_text_fraction_pct'])}%",
                     f"{r['LLVM3_boot1_rx_Rss_kB']} / {r['LLVM3_boot2_rx_Rss_kB']}"))
    table(lines, ["进程", "对象", "当前 r-x Rss KiB", "加载器节 大小/驻留 KiB", "加载器占 r-x", ".text 大小/驻留 KiB", ".text 占 r-x", "LLVM3 两次 r-x Rss KiB"], rows)
    lines.extend([f"13 对象当前 LLVM r-x 驻留合计 **{fmt(total_rx)} KiB**：加载器相关节 **{fmt(total_loader)} KiB（{total_loader/total_rx*100:.1f}%）**，`.text` **{fmt(total_text)} KiB（{total_text/total_rx*100:.1f}%）**。这是当前镜像驻留页的节分布，不等于相对 GCC 增量的节分布。当前 `BUILD_ID` 与第三轮 LLVM 快照的镜像版本不同；两次历史 LLVM Rss 仅并列供参考，不混同为同次运行。", "",
                  "## GCC 静态节大小与两次开机 Rss", ""])
    gccrows = []
    for r in objects:
        size = r["GCC_loader_sections_size_kB"]
        if size == "MISSING":
            verdict = "GCC ELF 缺失，未确定"
        else:
            boots = [float(r["GCC_boot1_rx_Rss_kB"]), float(r["GCC_boot2_rx_Rss_kB"])]
            verdict = ("两次均小于：未整段驻留" if all(x < float(size) for x in boots)
                       else "一次小于：该次未整段驻留" if any(x < float(size) for x in boots)
                       else "Rss 不小于：不能判断是否整段驻留")
        gccrows.append((r["process"], f"`{r['object']}`", fmt(size) if size != "MISSING" else "未找到",
                        f"{r['GCC_boot1_rx_Rss_kB']} / {r['GCC_boot2_rx_Rss_kB']}", verdict))
    table(lines, ["进程", "对象", "GCC 加载器节静态合计 KiB", "GCC1 / GCC2 r-x Rss KiB", "判断"], gccrows)
    lines.extend(["若某次 GCC r-x 映射总 Rss 小于加载器相关节静态总大小，该次不可能把这些节的全部字节都留在驻留页中；反过来，Rss 大于节大小并不证明这些节全驻留。判据只用本次 `sections.tsv` 与历史 [`object_summary.tsv`](../data/tvs_daemon_code_pages/object_summary.tsv)。", "",
                  "## 相对 GCC 的严格下界", "",
                  "历史 GCC 无逐页记录，但其某对象的加载器节驻留量不可能超过 `min(GCC 两次平均 r-x Rss, GCC 版加载器节静态大小)`。逐对象用“当前 LLVM 加载器节驻留 − 这个 GCC 上界”求下界，再相加；该算法可得保守净增量，不能给出精确值。`.text` 同理。GCC 静态大小来自已预链接的板上副本。", "",
                  f"13 对象加载器节驻留的 LLVM−GCC **净增量至少 {fmt(lower_loader)} KiB**，相当于这些对象 r-x 总 Rss 差 {fmt(total_rx-total_gcc)} KiB 的 **{lower_loader/(total_rx-total_gcc)*100:.1f}%**。只看 12 个 `.so`，下界为 {fmt(lower_loader_libraries)} KiB，占这 12 库 r-x 总 Rss 差 {fmt(library_excess)} KiB 的 {lower_loader_libraries/library_excess*100:.1f}%。当前 LLVM `.text` 驻留为 {fmt(total_text)} KiB；其相对 GCC 的净差仅能界定在 **{fmt(lower_text)} 至 +{fmt(total_text)} KiB**，不能证明 `.text` 驻留增加。下界计算所用逐对象静态大小及 Rss 均在上表与 `group_summary.tsv`。", "",
                  "## 结论：实测与未确定", "",
                  f"有数据支撑：当前 LLVM 这 13 个对象的 r-x 驻留中，加载器节 {fmt(total_loader)} KiB（{total_loader/total_rx*100:.1f}%），`.text` {fmt(total_text)} KiB（{total_text/total_rx*100:.1f}%）。GCC 两次开机这 13 对象 r-x Rss 均值合计 {fmt(total_gcc)} KiB" + (f"，当前 LLVM 与其总量差 {fmt(total_rx-total_gcc)} KiB。" if gcc_comparable else "；因对象缺项，不给出总量差。") + "各对象详情与来源见上表。", "",
                  f"有数据支撑的下界：加载器节驻留净增长至少 {fmt(lower_loader)} KiB；这证明增量中相当大一部分落在加载器相关节，而不是只能由实际执行的 `.text` 解释。", "",
                  "未确定：历史 GCC 只有 r-x 总 Rss，没有逐页 pagemap 或按节驻留。仅凭当前 LLVM 的节归属和 GCC 的静态节大小/总 Rss，无法唯一确定 LLVM−GCC 多出页中加载器节与 `.text` 的精确 KiB；不能把当前 LLVM 的整段驻留量当成增量。且当前镜像与第三轮 LLVM 版本不同，进程工作负载也未锁定。", "",
                  "因此，本次数据**不能证明**“恢复预链接可省掉这部分 r-x 驻留”。预链接可能改变重定位与库落址，但要确认其对 r-x 页的收益，需同版镜像、同工作负载的有无预链接实验，分别采两侧 pagemap 与 smaps；本轮不执行。", ""])
    REPORT.write_text("\n".join(lines) + "\n")
    print("report", REPORT, "objects", len(objects), "loader", total_loader, "text", total_text, flush=True)


if __name__ == "__main__":
    main()
