#!/usr/bin/env python3
"""Classify observed r-x changes and render the evidence report; no board access."""
import csv
import json
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
MEMDIFF = OUT.parents[1]
REPORT = MEMDIFF / "reports/tvs_daemon_code_pages.md"


def read(name):
    with (OUT / name).open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def table(lines, columns, rows):
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    lines.append("")


def fmt(value):
    return f"{float(value):,.1f}"


def main():
    objects = read("object_summary.tsv")
    coverage = read("other_coverage.tsv")
    elf = {(r["image"], r["object"]): r for r in read("top10_elf.tsv")}
    boot = json.loads((OUT / "sources.json").read_text())["boots"]
    classification = []
    for r in objects:
        delta_pss = float(r["delta_Pss_kB"])
        delta_rss = float(r["delta_Rss_kB"])
        mapper_delta = float(r["delta_mappers"])
        tolerance = max(16.0, 0.05 * float(r["GCC_mean_Rss_kB"]),
                        float(r["GCC_range_Rss_kB"]), float(r["LLVM_range_Rss_kB"]))
        if delta_pss > 0 and delta_rss > tolerance:
            label = "a: Rss 增加"
        elif delta_pss > 0 and abs(delta_rss) <= tolerance and mapper_delta < 0:
            label = "b: 驻留近似不变、映射进程减少"
        elif delta_pss < 0:
            label = "负向抵消"
        else:
            label = "未确定"
        classification.append({"process": r["process"], "object": r["object"],
                               "class": label, "delta_Pss_kB": delta_pss,
                               "delta_Rss_kB": delta_rss, "delta_mappers": mapper_delta,
                               "rss_tolerance_kB": round(tolerance, 3)})
    with (OUT / "object_classification.tsv").open("w", newline="") as f:
        fields = list(classification[0])
        w = csv.DictWriter(f, fields, delimiter="\t", lineterminator="\n")
        w.writeheader(); w.writerows(classification)
    lines = ["# tvs-daemon / tv-viewer 代码映射 Pss 差额拆分", "",
             "## 数据、配对与口径", "",
             "只读复算四份 `02_steady/smaps_raw.txt.gz`，每侧两次开机。进程按 `### PID 名称 主程序路径` 选中，与前次 `components_per_boot.tsv` 的进程配对及 `other` 分类完全相同；在 `other` 中只取主程序自身或 `.so` 文件的 `r-x` 映射。所有 KiB 数值均来自逐映射 smaps，不与 `smaps_rollup` 混合。对象按映射路径精确配对；一侧缺席记 0，不把同名不同路径合并。映射进程数是该次完整快照中映射同一路径 `r-x` 页的去重 PID 数，包含目标进程。", "",
             "四次原始快照："]
    for k, v in boot.items():
        lines.append(f"- {k}: [`{v}`](../{v})")
    lines.extend(["", "复算代码 [`analyze.py`](../data/tvs_daemon_code_pages/analyze.py)、[`build_report.py`](../data/tvs_daemon_code_pages/build_report.py)；逐次六指标和进程数见 [`object_per_boot.tsv`](../data/tvs_daemon_code_pages/object_per_boot.tsv)，均值/差值/两次极差见 [`object_summary.tsv`](../data/tvs_daemon_code_pages/object_summary.tsv)。`other` 的非目标映射残差见 [`other_coverage.tsv`](../data/tvs_daemon_code_pages/other_coverage.tsv)。", "",
                  "ELF 只读自 `data/gcc_baseline/elf/files`、`data/llvm_round3/elf/files` 的板上拉回副本，路径逐项配对；解析器为前几轮同一交叉 `armv7l-tizen-linux-gnueabi-readelf`（路径和版本见 [`sources.json`](../data/tvs_daemon_code_pages/sources.json)、[`readelf_version.txt`](../data/tvs_daemon_code_pages/readelf_version.txt)）。`.text` 取 `readelf -SW` 节大小；`r-x LOAD` 取 `readelf -lW` 所有执行 LOAD 的 FileSiz 之和。驻留比 = 两次平均 Rss KiB ÷ (`r-x LOAD` FileSiz / 1024)；Rss 按页取整，比例可受非 `.text` 页影响。RPM 所属取第三轮 LLVM 板上 `rpm -qf` 归档 [`library_union.tsv`](../data/prelink_overlay_prep/library_union.tsv)，主程序按前次板上包查询；GCC 侧包归属未独立复查。", "",
                  "GCC LTO 痕迹采用镜像大小分析的规则：保留的 `.strtab` 中有 `.lto_priv.`，或有 `.gnu.lto` 节，判为“有痕迹”；保留 `.symtab` 但未见上述痕迹，判“未见痕迹”；`.symtab` 已被 strip，则“无法判断”。未见痕迹也不等于构建时未做 LTO。LLVM clang 只按 `.comment` 是否含 `clang` 记录。原样 readelf 输出在本目录 `readelf_*.txt`，错误码和 stderr 同时保存。", "",
                  "## other 覆盖情况", ""])
    covrows = []
    for name in ("tvs-daemon", "tv-viewer"):
        r = [x for x in coverage if x["process"] == name]
        other = [int(x["other_Pss_kB"]) for x in r]
        rx = [int(x["object_rx_Pss_kB"]) for x in r]
        residual = [int(x["other_residual_Pss_kB"]) for x in r]
        covrows.append((name, " / ".join(map(str, other)), " / ".join(map(str, rx)),
                        fmt((other[2]+other[3]-other[0]-other[1])/2),
                        fmt((rx[2]+rx[3]-rx[0]-rx[1])/2),
                        fmt((residual[2]+residual[3]-residual[0]-residual[1])/2)))
    table(lines, ["进程", "other GCC1/GCC2/LLVM1/LLVM2 Pss KiB", "对象 r-x 同序 Pss KiB", "other 差 KiB", "r-x 对象差 KiB", "非目标残差差 KiB"], covrows)
    lines.extend(["tvs-daemon 的 `other` 差额是 +5,768.5 KiB（约 5.63 MiB）；前次全进程 Pss+SwapPss 总差为 +6,603.5 KiB，两个口径不同。", "",
                  "## 对象 Pss 增量前 20", ""])
    for name in ("tvs-daemon", "tv-viewer"):
        subset = [r for r in objects if r["process"] == name]
        top = subset[:20]
        other_values = [int(x["other_Pss_kB"]) for x in coverage if x["process"] == name]
        other_delta = (other_values[2]+other_values[3]-other_values[0]-other_values[1])/2
        total_top = sum(float(r["delta_Pss_kB"]) for r in top)
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"前 20 对象 Pss 差合计 {fmt(total_top)} KiB，占 `other` 差额 {total_top/other_delta*100:.1f}%（分母 {fmt(other_delta)} KiB）。下表按正向差值排序；逐次值、六项指标和映射进程数均在 `object_summary.tsv`。")
        lines.append("")
        rows = []
        for r in top:
            cls = next(x["class"] for x in classification if x["process"] == name and x["object"] == r["object"])
            rows.append((f"`{r['object']}`", "/".join(r[f"{b}_Pss_kB"] for b in boot),
                         f"{fmt(r['GCC_mean_Pss_kB'])} / {fmt(r['LLVM_mean_Pss_kB'])}",
                         fmt(r["delta_Pss_kB"]), fmt(r["delta_Rss_kB"]),
                         f"{fmt(r['GCC_mean_mappers'])} / {fmt(r['LLVM_mean_mappers'])}", cls))
        table(lines, ["对象", "四次 Pss KiB", "GCC/LLVM 均值 KiB", "ΔPss KiB", "ΔRss KiB", "映射进程 GCC/LLVM 均值", "观察分类"], rows)
    lines.extend(["## 前 10 对象 ELF 体积与驻留", "",
                  "完整两侧 `.text`、LOAD、编译器信息和 readelf 状态在 [`top10_elf.tsv`](../data/tvs_daemon_code_pages/top10_elf.tsv)。缺失 ELF 时明确标为 MISSING；本次前 10 对象的两侧 ELF 均存在。", ""])
    for name in ("tvs-daemon", "tv-viewer"):
        lines.append(f"### {name}")
        lines.append("")
        rows = []
        for r in [x for x in objects if x["process"] == name][:10]:
            g = elf[("GCC", r["object"])]
            l = elf[("LLVM", r["object"])]
            def ratio(e, image):
                size = float(e.get("rx_load_filesz_bytes") or 0)
                return f"{float(r[image+'_mean_Rss_kB'])/(size/1024)*100:.1f}%" if size else "未确定"
            rows.append((f"`{r['object']}`", f"{int(g['text_bytes'])/1024:.1f} / {int(l['text_bytes'])/1024:.1f}",
                         f"{int(g['rx_load_filesz_bytes'])/1024:.1f} / {int(l['rx_load_filesz_bytes'])/1024:.1f}",
                         f"{fmt(r['GCC_mean_Rss_kB'])} / {fmt(r['LLVM_mean_Rss_kB'])}",
                         f"{ratio(g, 'GCC')} / {ratio(l, 'LLVM')}", g["gcc_lto_trace"], l["llvm_clang_comment"], l["rpm"]))
        table(lines, ["对象", ".text GCC/LLVM KiB", "r-x LOAD GCC/LLVM KiB", "Rss GCC/LLVM KiB", "驻留比 GCC/LLVM", "GCC LTO 痕迹", "LLVM clang", "RPM"], rows)
    lines.extend(["## 驻留增加与共享分摊", "",
                  "观察分类规则：只对正的对象 ΔPss 计入 (a)/(b)；Rss “基本不变”的容差为 `max(16 KiB, GCC 平均 Rss 的 5%, GCC 两次 Rss 极差, LLVM 两次 Rss 极差)`。(a) 为 ΔRss 高于容差；(b) 为 |ΔRss| 不高于容差且完整快照中映射进程数下降。其余正值记“未确定”，负值单列抵消。这个规则用 Rss 与共享数识别模式，不能单凭汇总量证明逐页因果关系，尤其 (b) 的实际共享页集合仍可能不同。逐对象判别与容差在 [`object_classification.tsv`](../data/tvs_daemon_code_pages/object_classification.tsv)。", ""])
    sums = defaultdict(lambda: defaultdict(float))
    for c in classification:
        sums[c["process"]][c["class"]] += c["delta_Pss_kB"]
    table(lines, ["进程", "(a) Rss 增加 KiB", "(b) 分摊模式 KiB", "未确定正差 KiB", "负向抵消 KiB", "对象净差 KiB"],
          [(n, *(fmt(sums[n][k]) for k in ("a: Rss 增加", "b: 驻留近似不变、映射进程减少", "未确定", "负向抵消")),
            fmt(sum(sums[n].values()))) for n in ("tvs-daemon", "tv-viewer")])
    lines.extend(["## 有数据支撑的结论与限制", "",
                  "- tvs-daemon 最大五项依次为 `libtvs-api-native.so` +452、`libtvs-dvb-si.so` +372、`libtvs-iss.so` +352、`libtvs-util.so` +344、`libtvs-dsm.so` +324 KiB；五项的 Rss 各自同量增加，且两侧映射进程数均为 1，属于 (a) 观察模式。GCC 板上这五个 ELF 都无 `.symtab`，按规定的痕迹规则无法判定是否做过 LTO。", "",
                  "- tvs-daemon 全部 r-x 对象正差中 (a) 合计 +5,446.0 KiB；(b) +351.5 KiB，其中 `libgstreamer-1.0.so.0.2411.0` +290.5 KiB（Rss −14 KiB，映射进程 6→5），是共享分摊模式，不能作为代码体积增长。其余正差 +99.0 KiB 未确定，负向抵消 −128.0 KiB。加总为对象净差 +5,768.5 KiB。", "",
                  "- 前五个对象 LLVM `.text` 均小于 GCC，但驻留 Rss/Pss 增加；已有数据能证明驻留变多，不能确定是代码路径、缓存状态、进程工作负载还是构建方式导致。前十对象的 GCC LTO 痕迹全部因 `.symtab` 缺失而无法判断；不能把 (a) 直接归因于 LTO。", "",
                  "- 两镜像服务集合和启动时点可能不同；这里只有同名同主程序的目标进程配对与两次快照，未对代码页的实际访问路径做追踪。", ""])
    REPORT.write_text("\n".join(lines) + "\n")
    print("report", REPORT, "classifications", len(classification), flush=True)


if __name__ == "__main__":
    main()
