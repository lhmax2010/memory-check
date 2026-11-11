# 当前 VD LLVM 镜像代码映射驻留页的 ELF 节归属

## 身份、来源和采集质量

板子 IP `192.168.108.26`；`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`；开机 ID `0d30d3eb-a65b-44e2-b1d6-ee93e2c39af5`；采集窗口 UTC `2026-11-11T12:29:59.723982+00:00` 至 `2026-11-11T12:30:16.323494+00:00`。四项身份和 BUILD_ID 检查均通过，使用 `sdb root on` 只读采集，结束 `root off` 后 UID 恢复到 `5001`（见 [`collection.json`](../data/code_page_sections/collection.json) 和原始命令输出）。未重启、未在板上创建或修改文件。

目标清单实际为 **13** 个对象（tvs-daemon 10 个库，tv-viewer 1 个可执行文件与 2 个库；任务文字中的“12 个”与清单不一致，本报告按清单全数处理）。进程 PID：tvs-daemon=691, tv-viewer=548。

板上原始 `maps`、采集前后 `smaps`、每个 VMA 一次 `dd` 读取的完整 pagemap 十六进制输出及每条命令返回码在 [`raw/`](../data/code_page_sections/raw/) 和 `collection.json`。13 份 ELF 由 `sdb pull` 原样拉回，板上与主机 SHA256 逐项一致；哈希见 `collection.json`，文件在 [`elf/`](../data/code_page_sections/elf/)。解析器为前几轮同一交叉 readelf；逐对象 `-SW`/`-lW` 原始输出在 [`readelf/`](../data/code_page_sections/readelf/)。

与第三轮 LLVM 的 ELF SHA256 逐项比较：12 个相同、1 个不同；不同项及两侧哈希见 [`current_vs_llvm3_elf.tsv`](../data/code_page_sections/current_vs_llvm3_elf.tsv)。镜像 BUILD_ID 仍不同，不能据此认为运行环境完全相同。

每个映射的 `Rss`/`Pss`/`Private_Dirty` 对照和 pagemap present/swapped 页数见 [`mappings.tsv`](../data/code_page_sections/mappings.tsv)。39 个 VMA 共记录到 3 个 swapped 页；swapped 页不计入当前驻留。pagemap 采样与 smaps 读取不是原子操作；以超过 4 KiB 为准，没有 VMA 出现超过 4 KiB 的 present×页大小与 smaps Rss 差异。

## 归属算法及限制

对每个文件映射 VMA，用 `maps` 起止地址和文件偏移算页号；`dd if=/proc/PID/pagemap bs=8 skip=... count=... | od -An -tx8 -v` 一次读取该 VMA 全段。bit 63 为 present、bit 62 为 swapped。present 页在文件中的区间是 `[VMA 文件偏移 + 页序号×页大小, +页大小)`；与 `readelf -SW` 节的文件偏移/大小做字节区间交集。跨节页按交集字节数分摊 KiB；不属于任何节的头部、对齐填充计“其余”。`.bss/.tbss` 为 NOBITS，列静态大小，但文件页不归入它们；匿名扩展页不在本次文件映射范围。每个 VMA 的页归属总量与 present×页大小守恒检查由 [`analyze.py`](../data/code_page_sections/analyze.py) 执行。

按节明细见 [`sections.tsv`](../data/code_page_sections/sections.tsv)（GCC/当前 LLVM 节大小）、[`section_residency.tsv`](../data/code_page_sections/section_residency.tsv)（各 VMA 权限下逐节驻留）、[`group_summary.tsv`](../data/code_page_sections/group_summary.tsv)（逐组及权限）、[`object_sections_wide.tsv`](../data/code_page_sections/object_sections_wide.tsv)（每个对象一行，所有组的大小和驻留）。加载器相关节仅指 `.dynsym`、`.dynstr`、`.gnu.hash/.hash`、`.gnu.version*`、`.rel.dyn`、`.rel.plt`；`.plt` 单列为代码，不并入加载器表。

## 逐对象当前 LLVM 驻留

| 进程 | 对象 | 当前 r-x Rss KiB | 加载器节 大小/驻留 KiB | 加载器占 r-x | .text 大小/驻留 KiB | .text 占 r-x | LLVM3 两次 r-x Rss KiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tv-viewer | `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | 2,436.0 | 1,081.9 / 589.9 | 24.2% | 4,691.7 / 1,528.3 | 62.7% | 2432 / 2432 |
| tv-viewer | `/usr/lib/libtvs-api.so` | 860.0 | 660.2 / 612.2 | 71.2% | 618.6 / 162.6 | 18.9% | 860 / 860 |
| tv-viewer | `/usr/lib/libtvs-parser.so` | 480.0 | 462.0 / 446.0 | 92.9% | 322.7 / 16.1 | 3.4% | 480 / 480 |
| tvs-daemon | `/usr/lib/libtvs-api-native.so` | 1,060.0 | 546.0 / 546.0 | 51.5% | 596.8 / 356.8 | 33.7% | 1052 / 1052 |
| tvs-daemon | `/usr/lib/libtvs-atsc30-parser.so` | 240.0 | 223.8 / 223.8 | 93.2% | 238.5 / 4.3 | 1.8% | 240 / 240 |
| tvs-daemon | `/usr/lib/libtvs-b2b.so` | 432.0 | 329.5 / 325.5 | 75.4% | 195.1 / 59.1 | 13.7% | 432 / 432 |
| tvs-daemon | `/usr/lib/libtvs-dsm.so` | 380.0 | 340.9 / 340.9 | 89.7% | 494.0 / 12.0 | 3.2% | 380 / 380 |
| tvs-daemon | `/usr/lib/libtvs-dvb-si.so` | 408.0 | 381.5 / 373.5 | 91.5% | 377.6 / 11.5 | 2.8% | 408 / 408 |
| tvs-daemon | `/usr/lib/libtvs-dvbbase-scan.so` | 248.0 | 235.3 / 235.3 | 94.9% | 248.0 / 1.3 | 0.5% | 248 / 248 |
| tvs-daemon | `/usr/lib/libtvs-ext.so` | 440.0 | 271.8 / 263.8 | 60.0% | 281.4 / 109.4 | 24.9% | 440 / 440 |
| tvs-daemon | `/usr/lib/libtvs-iss.so` | 764.0 | 454.1 / 442.1 | 57.9% | 433.3 / 201.3 | 26.3% | 764 / 764 |
| tvs-daemon | `/usr/lib/libtvs-si.so` | 264.0 | 214.4 / 214.4 | 81.2% | 202.6 / 28.0 | 10.6% | 264 / 264 |
| tvs-daemon | `/usr/lib/libtvs-util.so` | 808.0 | 440.2 / 428.2 | 53.0% | 390.2 / 254.2 | 31.5% | 808 / 808 |

13 对象当前 LLVM r-x 驻留合计 **8,820.0 KiB**：加载器相关节 **5,041.7 KiB（57.2%）**，`.text` **2,744.9 KiB（31.1%）**。这是当前镜像驻留页的节分布，不等于相对 GCC 增量的节分布。当前 `BUILD_ID` 与第三轮 LLVM 快照的镜像版本不同；两次历史 LLVM Rss 仅并列供参考，不混同为同次运行。

## GCC 静态节大小与两次开机 Rss

| 进程 | 对象 | GCC 加载器节静态合计 KiB | GCC1 / GCC2 r-x Rss KiB | 判断 |
| --- | --- | --- | --- | --- |
| tv-viewer | `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | 876.7 | 2024 / 2012 | Rss 不小于：不能判断是否整段驻留 |
| tv-viewer | `/usr/lib/libtvs-api.so` | 351.8 | 264 / 264 | 两次均小于：未整段驻留 |
| tv-viewer | `/usr/lib/libtvs-parser.so` | 342.9 | 56 / 56 | 两次均小于：未整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-api-native.so` | 305.1 | 604 / 596 | Rss 不小于：不能判断是否整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-atsc30-parser.so` | 155.0 | 32 / 32 | 两次均小于：未整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-b2b.so` | 171.1 | 128 / 128 | 两次均小于：未整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-dsm.so` | 229.8 | 56 / 56 | 两次均小于：未整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-dvb-si.so` | 183.8 | 36 / 36 | 两次均小于：未整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-dvbbase-scan.so` | 169.3 | 36 / 36 | 两次均小于：未整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-ext.so` | 151.2 | 232 / 232 | Rss 不小于：不能判断是否整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-iss.so` | 216.1 | 412 / 412 | Rss 不小于：不能判断是否整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-si.so` | 170.8 | 56 / 56 | 两次均小于：未整段驻留 |
| tvs-daemon | `/usr/lib/libtvs-util.so` | 237.9 | 464 / 464 | Rss 不小于：不能判断是否整段驻留 |

若某次 GCC r-x 映射总 Rss 小于加载器相关节静态总大小，该次不可能把这些节的全部字节都留在驻留页中；反过来，Rss 大于节大小并不证明这些节全驻留。判据只用本次 `sections.tsv` 与历史 [`object_summary.tsv`](../data/tvs_daemon_code_pages/object_summary.tsv)。

## 相对 GCC 的严格下界

历史 GCC 无逐页记录，但其某对象的加载器节驻留量不可能超过 `min(GCC 两次平均 r-x Rss, GCC 版加载器节静态大小)`。逐对象用“当前 LLVM 加载器节驻留 − 这个 GCC 上界”求下界，再相加；该算法可得保守净增量，不能给出精确值。`.text` 同理。GCC 静态大小来自已预链接的板上副本。

13 对象加载器节驻留的 LLVM−GCC **净增量至少 2,590.6 KiB**，相当于这些对象 r-x 总 Rss 差 4,430.0 KiB 的 **58.5%**。只看 12 个 `.so`，下界为 2,877.4 KiB，占这 12 库 r-x 总 Rss 差 4,012.0 KiB 的 71.7%。当前 LLVM `.text` 驻留为 2,744.9 KiB；其相对 GCC 的净差仅能界定在 **-1,645.1 至 +2,744.9 KiB**，不能证明 `.text` 驻留增加。下界计算所用逐对象静态大小及 Rss 均在上表与 `group_summary.tsv`。

## 结论：实测与未确定

有数据支撑：当前 LLVM 这 13 个对象的 r-x 驻留中，加载器节 5,041.7 KiB（57.2%），`.text` 2,744.9 KiB（31.1%）。GCC 两次开机这 13 对象 r-x Rss 均值合计 4,390.0 KiB，当前 LLVM 与其总量差 4,430.0 KiB。各对象详情与来源见上表。

有数据支撑的下界：加载器节驻留净增长至少 2,590.6 KiB；这证明增量中相当大一部分落在加载器相关节，而不是只能由实际执行的 `.text` 解释。

未确定：历史 GCC 只有 r-x 总 Rss，没有逐页 pagemap 或按节驻留。仅凭当前 LLVM 的节归属和 GCC 的静态节大小/总 Rss，无法唯一确定 LLVM−GCC 多出页中加载器节与 `.text` 的精确 KiB；不能把当前 LLVM 的整段驻留量当成增量。且当前镜像与第三轮 LLVM 版本不同，进程工作负载也未锁定。

因此，本次数据**不能证明**“恢复预链接可省掉这部分 r-x 驻留”。预链接可能改变重定位与库落址，但要确认其对 r-x 页的收益，需同版镜像、同工作负载的有无预链接实验，分别采两侧 pagemap 与 smaps；本轮不执行。

