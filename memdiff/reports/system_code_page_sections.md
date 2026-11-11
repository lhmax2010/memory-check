# VD LLVM 全系统 r-x 驻留页 ELF 节归属及 GCC 对照

## 采集范围与质量

板子 `192.168.108.26`；BUILD_ID `T-KSU2EJAKUC-0101-PERF-202611061751` 与上一轮一致；armv7l、NT72671D、KSU2E、clang 内核四项均通过。初始 PID 322 个，完整采集 316 个，退出或不完整 6 个；不重试。唯一映射路径 1555 个，拉回且 SHA256 一致 1549 个、失败 6 个，其中 ELF 1452 个。`sdb root off` 后 UID 恢复、boot ID 未变。每个 PID 只开一个 SDB shell 会话，逐 r-xp 文件 VMA 执行一次 `dd /proc/PID/pagemap | od`；原始 maps/smaps/pagemap、命令及返回码见 [`collection.json`](../data/system_code_page_sections/collection.json) 与 `raw/`。

解析出 16414 个 r-xp 文件 VMA，pagemap present×页大小与同 VMA smaps Rss 不一致的有 0 个。进程状态和失败列表见 [`process_parse_errors.tsv`](../data/system_code_page_sections/process_parse_errors.tsv)，ELF 拉取失败/非 ELF/哈希状态见 `collection.json`。开发机 CPU0、nice19、串行、Python 虚拟内存上限 2.5 GB。采集前后未在板上写文件、未重启。

## 逐页算法与文件集合

沿用上一轮 [`analyze.py`](../data/code_page_sections/analyze.py) 的节归属规则：每个 present 页按映射文件偏移与 `readelf -SW` 的节区间相交；跨节页按交集字节数分摊，不属于节的字节计入“其余”。加载器相关节仅 `.dynsym/.dynstr/.gnu.hash/.hash/.gnu.version*/.rel.dyn/.rel.plt`；`.plt` 不并入。逐 PID 原始数据经 [`parse_pages.py`](../data/system_code_page_sections/parse_pages.py) 转为 [`vmas.tsv`](../data/system_code_page_sections/vmas.tsv)、[`unique_pages.tsv.gz`](../data/system_code_page_sections/unique_pages.tsv.gz)；逐节驻留见 [`section_residency.tsv`](../data/system_code_page_sections/section_residency.tsv)，完整逐文件表见 [`file_residency.tsv`](../data/system_code_page_sections/file_residency.tsv)。

对同一路径的所有 present r-xp 页以文件偏移取并集；遇到 r-x Private_Dirty、DT_TEXTREL、同路径多个 dev/inode、同 inode 多路径别名或已删除映射，文件单列且不参与可信总量。GCC 采用两次 `02_steady/smaps_raw.txt.gz` 中该路径全部 r-xp VMA 的 Pss 之和；Pss 逐映射舍入使它只近似文件唯一驻留量。两边文件路径取交集，且当前文件必须是哈希一致、可解析的 ELF，才进入下表；GCC 静态节缺失或读取错误亦排除。全路径共 1651，两侧都出现 1474，可信共同文件 1360；单侧文件见 [`single_side_files.tsv`](../data/system_code_page_sections/single_side_files.tsv)。共同文件的排除原因统计：missing_GCC_ELF_copy=19；missing_or_nonELF_current_copy,missing_current_sections=2；missing_or_nonELF_current_copy,missing_current_sections,missing_GCC_ELF_copy=81；rx_Private_Dirty,DT_TEXTREL=1；rx_Private_Dirty,missing_or_nonELF_current_copy,missing_current_sections,missing_GCC_ELF_copy=3；same_inode_multiple_paths=4；same_inode_multiple_paths,missing_or_nonELF_current_copy,missing_current_sections,missing_GCC_ELF_copy=4。同 inode 别名见 [`inode_path_aliases.tsv`](../data/system_code_page_sections/inode_path_aliases.tsv)。

被排除的共同文件 114 个，原始偏移并集读数合计 11,020.0 KiB、GCC Pss 均值 10,069.0 KiB；因非 ELF、缺副本或不可可靠去重，不能加入下面的 ELF 节归属汇总。

## 第一部分：全系统与 prelink.conf 子集

| 集合 | 文件数 | LLVM 唯一 r-x KiB | GCC1 / GCC2 r-x Pss 和 KiB | GCC 均值 KiB | LLVM−GCC KiB | LLVM 加载器节 KiB | 加载器净增严格下界 KiB | 去加载器后 ≤ GCC / > GCC 文件数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| common_eligible | 1360 | 191,844.0 | 177,070.0 / 172,715.0 | 174,892.5 | 16,951.5 | 62,256.4 | 8,902.4 | 1102 / 258 |
| common_eligible_prelink_dirs | 1072 | 124,320.0 | 109,344.0 / 105,350.0 | 107,347.0 | 16,973.0 | 47,686.0 | 10,322.1 | 831 / 241 |

`prelink.conf` 内以板上原文的 8 条 `-l` 目录为准，见 [`prelink_dirs.json`](../data/system_code_page_sections/prelink_dirs.json)。加载器节净增下界逐文件计算为 `LLVM 已驻留加载器节 − min(GCC 两次平均 r-x Pss 和, GCC 板上副本加载器节静态大小)`，可为负；汇总为这些逐文件下界之和。GCC 副本已被出镜像 prelink 处理，且 Pss 有舍入，因此“严格”指按该证据口径的数学上界，不是同镜像干预实验的收益。

去加载器节后仍大于 GCC 的文件，差值最大的前 20 个：
| 文件 | LLVM 去加载器节后 − GCC KiB | LLVM 唯一 r-x KiB | GCC 均值 KiB |
| --- | --- | --- | --- |
| `/usr/lib/driver/libmali.so` | 661.1 | 10,024.0 | 8,940.5 |
| `/usr/lib/libavformat.so.61.7.100` | 268.4 | 348.0 | 44.0 |
| `/usr/lib/libavcodec.so.61.19.100` | 183.7 | 348.0 | 81.0 |
| `/opt/usr/apps/com.samsung.tv.ContentsBrowser/shared/res/libcompcb.so` | 169.8 | 1,720.0 | 1,340.0 |
| `/usr/lib/libGLESv2.so.2.0` | 131.5 | 216.0 | 66.5 |
| `/usr/lib/librlottie.so.0.2` | 131.4 | 144.0 | 0.0 |
| `/usr/lib/libturbojpeg.so.0.3.0` | 131.3 | 140.0 | 0.0 |
| `/usr/lib/libcairo.so.2.11400.2` | 103.8 | 192.0 | 46.0 |
| `/usr/bin/avocd` | 100.3 | 1,080.0 | 894.0 |
| `/usr/lib/libavutil.so.59.39.100` | 91.8 | 192.0 | 54.0 |
| `/usr/lib/libflux-manager.so.0.1.0` | 89.4 | 364.0 | 165.0 |
| `/opt/usr/apps/com.samsung.tizen.contextengine/bin/contextengine` | 87.2 | 548.0 | 440.0 |
| `/usr/lib/libcsf-thumbnail.so.25.02.03.1` | 81.2 | 308.0 | 116.0 |
| `/usr/lib/libcsf-content-agent.so.25.02.03.1` | 79.9 | 620.0 | 288.0 |
| `/usr/lib/libcapi-content-media-content.so.0.6.12` | 55.6 | 108.0 | 32.0 |
| `/usr/lib/ld-linux.so.3` | 53.8 | 160.0 | 104.0 |
| `/usr/lib/libbuxton2.so.1.1` | 49.9 | 60.0 | 0.0 |
| `/opt/usr/apps/com.samsung.tv.multiprofile-service/bin/multiprofile-serviceapp` | 47.7 | 724.0 | 646.0 |
| `/usr/lib/systemd/systemd` | 46.0 | 660.0 | 524.0 |
| `/usr/lib/libvconf.so.0.3.1` | 40.8 | 52.0 | 0.0 |

完整逐文件判断在 `file_residency.tsv`；以上差值可能受不同 BUILD_ID、进程集合和工作负载影响，不把它归因于编译器。

### 与周报 `+5.2 MiB` 对账

[`weekly_data_table.md`](../reports/weekly_data_table.md) 第 149–160 行的 +5.168457 MiB = +5,292.5 KiB，来源 [`clang_matched_paths_summary.tsv`](../data/llvm_round3/analysis/clang_matched_paths_summary.tsv) 的 `matched_all_four/code_r-x/Pss`：1292 个四次都匹配、第三轮 LLVM `.comment` 含 clang 的路径，逐映射 smaps Pss 求和；GCC/LLVM3 两次均值为 143,914.5/149,207.0 KiB。它不是全系统文件偏移去重的 Rss。

本次按相同的历史路径集合和逐映射 Pss 口径重算当前板：1291 个路径仍在、1 个缺席，Pss 和 153,827.0 KiB；相对同一 GCC 历史均值为 +9,912.5 KiB。此数可对账口径，但当前板 BUILD_ID 比第三轮新、运行进程集合不同、采集时刻不同，不能解释为编译器收益。文件路径集合与口径明细见 [`weekly_reconciliation.json`](../data/system_code_page_sections/weekly_reconciliation.json)。

## 第二部分：预链接标记与 .rel.dyn 类型

| 镜像副本 | 带任一预链接标记 / 全 ELF | .rel.dyn REL / RELA / 缺失 |
| --- | --- | --- |
| GCC | 425 / 1463 | 1300 / 163 / 0 |
| LLVM | 0 / 1452 | 1452 / 0 / 0 |

| 镜像副本 | .gnu.prelink_undo | .gnu.liblist | .gnu.conflict | GNU_PRELINKED | GNU_LIBLIST | CHECKSUM |
| --- | --- | --- | --- | --- | --- | --- |
| GCC | 425 | 424 | 10 | 415 | 10 | 415 |
| LLVM | 0 | 0 | 0 | 0 | 0 | 0 |

标记指 `.gnu.prelink_undo/.gnu.liblist/.gnu.conflict` 节或动态段 `GNU_PRELINKED/GNU_LIBLIST/CHECKSUM` 任一项。每个 ELF 的六项布尔值、`.rel.dyn` 类型和 readelf 返回码见 [`elf_summary.tsv`](../data/system_code_page_sections/elf_summary.tsv)。GCC 无标记与 LLVM 有标记的例外全表见 [`prelink_marker_exceptions.tsv`](../data/system_code_page_sections/prelink_marker_exceptions.tsv)；readelf 错误原文见 [`readelf_errors.tsv`](../data/system_code_page_sections/readelf_errors.tsv)。只记录标记，不由标记推断加载器运行时是否采用预链接。

## 第三部分：动态表与额外导出符号

两侧都有 ELF 副本的路径 1365 个。逐 ELF 的已定义 GLOBAL/WEAK、未定义符号和 `.dynstr/.dynsym/.rel.plt/.plt` 大小见 [`paired_dynamic.tsv`](../data/system_code_page_sections/paired_dynamic.tsv)，原始 `.dynsym` 条目在 [`dynsym_symbols.tsv.gz`](../data/system_code_page_sections/dynsym_symbols.tsv.gz)。额外导出符号按名称精确集合差比较（DEFAULT/PROTECTED 可见且已定义），再用 GBS root 交叉 `c++filt` 反解，逐符号见 [`llvm_extra_exported_symbols.tsv.gz`](../data/system_code_page_sections/llvm_extra_exported_symbols.tsv.gz)。

### 上一轮 13 个对象

| 对象 | 已定义 WEAK GCC/LLVM | 已定义 GLOBAL GCC/LLVM | 未定义 GCC/LLVM | .dynstr/.dynsym/.rel.plt/.plt GCC→LLVM KiB | LLVM 额外导出名数 |
| --- | --- | --- | --- | --- | --- |
| `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | 2435 / 3099 | 6242 / 6153 | 1161 / 1212 | 632.4→739.3 / 155.6→163.5 / 9.0→8.9 / 13.8→13.3 | 1266 |
| `/usr/lib/libtvs-api-native.so` | 0 / 2590 | 2662 / 2091 | 577 / 580 | 175.7→372.3 / 50.7→82.2 / 11.1→19.6 / 19.6→32.5 | 2182 |
| `/usr/lib/libtvs-api.so` | 0 / 3178 | 3583 / 3012 | 120 / 120 | 172.6→431.3 / 57.9→98.6 / 5.4→16.3 / 8.5→25.8 | 2608 |
| `/usr/lib/libtvs-atsc30-parser.so` | 0 / 1037 | 1993 / 1905 | 119 / 112 | 69.6→124.4 / 33.0→47.8 / 4.5→7.3 / 7.2→11.6 | 952 |
| `/usr/lib/libtvs-b2b.so` | 0 / 1101 | 1024 / 837 | 819 / 806 | 89.2→235.2 / 28.8→42.9 / 4.2→7.5 / 6.6→11.7 | 918 |
| `/usr/lib/libtvs-dsm.so` | 0 / 1104 | 2646 / 2544 | 344 / 335 | 123.6→214.0 / 46.8→62.3 / 11.5→17.0 / 17.9→26.7 | 1009 |
| `/usr/lib/libtvs-dvb-si.so` | 0 / 1485 | 1180 / 1108 | 487 / 476 | 96.3→242.0 / 26.1→48.0 / 4.9→14.5 / 7.5→22.7 | 1417 |
| `/usr/lib/libtvs-dvbbase-scan.so` | 0 / 1003 | 1198 / 1067 | 452 / 454 | 79.6→138.6 / 25.8→39.5 / 4.5→7.1 / 7.0→11.0 | 877 |
| `/usr/lib/libtvs-ext.so` | 0 / 1059 | 1237 / 1057 | 415 / 410 | 82.3→187.2 / 25.9→39.5 / 5.4→9.0 / 8.5→14.0 | 886 |
| `/usr/lib/libtvs-iss.so` | 0 / 2061 | 2116 / 1886 | 469 / 463 | 114.4→311.4 / 40.4→69.0 / 6.4→17.1 / 9.8→26.5 | 1834 |
| `/usr/lib/libtvs-parser.so` | 837 / 1717 | 3269 / 3270 | 170 / 169 | 173.5→286.3 / 67.2→80.6 / 9.6→16.2 / 14.8→25.6 | 1009 |
| `/usr/lib/libtvs-si.so` | 806 / 1103 | 639 / 638 | 358 / 349 | 103.5→143.7 / 28.3→32.7 / 5.1→8.5 / 7.9→13.3 | 503 |
| `/usr/lib/libtvs-util.so` | 0 / 1961 | 2376 / 2053 | 561 / 564 | 134.3→298.9 / 45.9→71.6 / 7.6→15.6 / 11.7→24.2 | 1656 |

13 对象的独立 TSV：[`thirteen_dynamic.tsv`](../data/system_code_page_sections/thirteen_dynamic.tsv)。

### 全部共同 ELF 合计

| 指标 | GCC | LLVM | LLVM−GCC | 单位 |
| --- | --- | --- | --- | --- |
| defined_GLOBAL | 381,312 | 357,204 | -24,108 | 个 |
| defined_WEAK | 62,857 | 188,193 | +125,336 | 个 |
| undefined | 199,813 | 198,128 | -1,685 | 个 |
| .dynstr_bytes | 30,728,675 | 42,059,980 | +11,331,305 | 字节 |
| .dynsym_bytes | 10,417,664 | 11,969,584 | +1,551,920 | 字节 |
| .rel.plt_bytes | 2,346,104 | 2,784,176 | +438,072 | 字节 |
| .plt_bytes | 3,694,100 | 4,376,336 | +682,236 | 字节 |

| LLVM 额外已定义导出名类别 | 数量 | 判定 |
| --- | --- | --- |
| vtable_typeinfo | 7,120 | 名称反解可识别 |
| template_instance_candidate | 82,861 | 按 <...> 名称模式，候选 |
| class_member_inline_unverified | 17,847 | 仅可确认是类成员函数；是否类内定义/inline 未确定 |
| class_member_inline_undetermined | 81 | 仅可确认是类成员函数；是否类内定义/inline 未确定 |
| other | 6,994 | 其他/未确定 |

额外导出名共 114,903 个；逐文件类别计数见 [`symbol_category_counts.tsv`](../data/system_code_page_sections/symbol_category_counts.tsv)。`c++filt` 只能给出名字，不能证明类成员函数是否在类内定义或是否 inline；这两类在报告中明确记为未确定，不作修改建议。符号版本后缀按 readelf 原样名称比较；版本差可能被计为额外名。构建根工具与 `LD_LIBRARY_PATH` 在 [`readelf_tool.txt`](../data/system_code_page_sections/readelf_tool.txt)。

