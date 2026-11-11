# tvs-daemon / tv-viewer 代码映射 Pss 差额拆分

## 数据、配对与口径

只读复算四份 `02_steady/smaps_raw.txt.gz`，每侧两次开机。进程按 `### PID 名称 主程序路径` 选中，与前次 `components_per_boot.tsv` 的进程配对及 `other` 分类完全相同；在 `other` 中只取主程序自身或 `.so` 文件的 `r-x` 映射。所有 KiB 数值均来自逐映射 smaps，不与 `smaps_rollup` 混合。对象按映射路径精确配对；一侧缺席记 0，不把同名不同路径合并。映射进程数是该次完整快照中映射同一路径 `r-x` 页的去重 PID 数，包含目标进程。

四次原始快照：
- GCC1: [`data/gcc_baseline/boot1/memcheck/gcc_boot1_20261102_182343/02_steady/smaps_raw.txt.gz`](../data/gcc_baseline/boot1/memcheck/gcc_boot1_20261102_182343/02_steady/smaps_raw.txt.gz)
- GCC2: [`data/gcc_baseline/boot2/memcheck/gcc_boot2_20261102_192351/02_steady/smaps_raw.txt.gz`](../data/gcc_baseline/boot2/memcheck/gcc_boot2_20261102_192351/02_steady/smaps_raw.txt.gz)
- LLVM1: [`data/llvm_round3/boot1/memcheck/llvm_boot1_20261103_015124/02_steady/smaps_raw.txt.gz`](../data/llvm_round3/boot1/memcheck/llvm_boot1_20261103_015124/02_steady/smaps_raw.txt.gz)
- LLVM2: [`data/llvm_round3/boot2/memcheck/llvm_boot2_20261103_030258/02_steady/smaps_raw.txt.gz`](../data/llvm_round3/boot2/memcheck/llvm_boot2_20261103_030258/02_steady/smaps_raw.txt.gz)

复算代码 [`analyze.py`](../data/tvs_daemon_code_pages/analyze.py)、[`build_report.py`](../data/tvs_daemon_code_pages/build_report.py)；逐次六指标和进程数见 [`object_per_boot.tsv`](../data/tvs_daemon_code_pages/object_per_boot.tsv)，均值/差值/两次极差见 [`object_summary.tsv`](../data/tvs_daemon_code_pages/object_summary.tsv)。`other` 的非目标映射残差见 [`other_coverage.tsv`](../data/tvs_daemon_code_pages/other_coverage.tsv)。

ELF 只读自 `data/gcc_baseline/elf/files`、`data/llvm_round3/elf/files` 的板上拉回副本，路径逐项配对；解析器为前几轮同一交叉 `armv7l-tizen-linux-gnueabi-readelf`（路径和版本见 [`sources.json`](../data/tvs_daemon_code_pages/sources.json)、[`readelf_version.txt`](../data/tvs_daemon_code_pages/readelf_version.txt)）。`.text` 取 `readelf -SW` 节大小；`r-x LOAD` 取 `readelf -lW` 所有执行 LOAD 的 FileSiz 之和。驻留比 = 两次平均 Rss KiB ÷ (`r-x LOAD` FileSiz / 1024)；Rss 按页取整，比例可受非 `.text` 页影响。RPM 所属取第三轮 LLVM 板上 `rpm -qf` 归档 [`library_union.tsv`](../data/prelink_overlay_prep/library_union.tsv)，主程序按前次板上包查询；GCC 侧包归属未独立复查。

GCC LTO 痕迹采用镜像大小分析的规则：保留的 `.strtab` 中有 `.lto_priv.`，或有 `.gnu.lto` 节，判为“有痕迹”；保留 `.symtab` 但未见上述痕迹，判“未见痕迹”；`.symtab` 已被 strip，则“无法判断”。未见痕迹也不等于构建时未做 LTO。LLVM clang 只按 `.comment` 是否含 `clang` 记录。原样 readelf 输出在本目录 `readelf_*.txt`，错误码和 stderr 同时保存。

## other 覆盖情况

| 进程 | other GCC1/GCC2/LLVM1/LLVM2 Pss KiB | 对象 r-x 同序 Pss KiB | other 差 KiB | r-x 对象差 KiB | 非目标残差差 KiB |
| --- | --- | --- | --- | --- | --- |
| tvs-daemon | 7958 / 7819 / 13657 / 13657 | 7926 / 7789 / 13626 / 13626 | 5,768.5 | 5,768.5 | 0.0 |
| tv-viewer | 4024 / 4070 / 5011 / 5010 | 3972 / 4007 / 4846 / 4845 | 963.5 | 856.0 | 107.5 |

tvs-daemon 的 `other` 差额是 +5,768.5 KiB（约 5.63 MiB）；前次全进程 Pss+SwapPss 总差为 +6,603.5 KiB，两个口径不同。

## 对象 Pss 增量前 20

### tvs-daemon

前 20 对象 Pss 差合计 4,414.5 KiB，占 `other` 差额 76.5%（分母 5,768.5 KiB）。下表按正向差值排序；逐次值、六项指标和映射进程数均在 `object_summary.tsv`。

| 对象 | 四次 Pss KiB | GCC/LLVM 均值 KiB | ΔPss KiB | ΔRss KiB | 映射进程 GCC/LLVM 均值 | 观察分类 |
| --- | --- | --- | --- | --- | --- | --- |
| `/usr/lib/libtvs-api-native.so` | 604/596/1052/1052 | 600.0 / 1,052.0 | 452.0 | 452.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-dvb-si.so` | 36/36/408/408 | 36.0 / 408.0 | 372.0 | 372.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-iss.so` | 412/412/764/764 | 412.0 / 764.0 | 352.0 | 352.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-util.so` | 464/464/808/808 | 464.0 / 808.0 | 344.0 | 344.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-dsm.so` | 56/56/380/380 | 56.0 / 380.0 | 324.0 | 324.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-b2b.so` | 128/128/432/432 | 128.0 / 432.0 | 304.0 | 304.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libgstreamer-1.0.so.0.2411.0` | 349/348/639/639 | 348.5 / 639.0 | 290.5 | -14.0 | 6.0 / 5.0 | b: 驻留近似不变、映射进程减少 |
| `/usr/lib/libtvs-dvbbase-scan.so` | 36/36/248/248 | 36.0 / 248.0 | 212.0 | 212.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-atsc30-parser.so` | 32/32/240/240 | 32.0 / 240.0 | 208.0 | 208.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-ext.so` | 232/232/440/440 | 232.0 / 440.0 | 208.0 | 208.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-si.so` | 56/56/264/264 | 56.0 / 264.0 | 208.0 | 208.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-dvbbase-si.so` | 36/36/236/236 | 36.0 / 236.0 | 200.0 | 200.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-chms.so` | 300/300/476/476 | 300.0 / 476.0 | 176.0 | 176.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-scan.so` | 140/140/272/272 | 140.0 / 272.0 | 132.0 | 132.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-live.so` | 636/620/756/756 | 628.0 / 756.0 | 128.0 | 128.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-atsc30-si.so` | 24/24/136/136 | 24.0 / 136.0 | 112.0 | 112.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-atsc30-live.so` | 68/68/172/172 | 68.0 / 172.0 | 104.0 | 104.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-dvbbase-guide.so` | 32/32/136/136 | 32.0 / 136.0 | 104.0 | 104.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-guide.so` | 136/136/228/228 | 136.0 / 228.0 | 92.0 | 92.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtvs-isdb-si.so` | 20/20/112/112 | 20.0 / 112.0 | 92.0 | 92.0 | 1.0 / 1.0 | a: Rss 增加 |

### tv-viewer

前 20 对象 Pss 差合计 825.5 KiB，占 `other` 差额 85.7%（分母 963.5 KiB）。下表按正向差值排序；逐次值、六项指标和映射进程数均在 `object_summary.tsv`。

| 对象 | 四次 Pss KiB | GCC/LLVM 均值 KiB | ΔPss KiB | ΔRss KiB | 映射进程 GCC/LLVM 均值 | 观察分类 |
| --- | --- | --- | --- | --- | --- | --- |
| `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | 2024/2012/2432/2432 | 2,018.0 / 2,432.0 | 414.0 | 414.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libreminder-api.so.0.1.0` | 16/16/76/76 | 16.0 / 76.0 | 60.0 | 104.0 | 2.0 / 2.0 | a: Rss 增加 |
| `/usr/lib/libtvs-parser.so` | 17/17/77/77 | 17.0 / 77.0 | 60.0 | 424.0 | 8.0 / 8.0 | a: Rss 增加 |
| `/usr/lib/libtv-viewer-kevent.so.0.1.0` | 40/40/84/84 | 40.0 / 84.0 | 44.0 | 44.0 | 1.0 / 1.0 | a: Rss 增加 |
| `/usr/lib/libtv-viewer-api.so.0.1.0` | 42/48/74/74 | 45.0 / 74.0 | 29.0 | 56.0 | 2.5 / 2.0 | a: Rss 增加 |
| `/usr/lib/libtvs-api.so` | 16/16/45/45 | 16.0 / 45.0 | 29.0 | 596.0 | 25.0 / 24.0 | a: Rss 增加 |
| `/usr/lib/libbms-api.so` | 7/7/34/34 | 7.0 / 34.0 | 27.0 | 80.0 | 3.0 / 3.0 | a: Rss 增加 |
| `/usr/lib/libtvs-ht-api.so` | 13/13/35/35 | 13.0 / 35.0 | 22.0 | 136.0 | 6.0 / 6.0 | a: Rss 增加 |
| `/usr/lib/libflux-manager.so.0.1.0` | 39/39/58/58 | 39.0 / 58.0 | 19.0 | 80.0 | 4.0 / 4.0 | a: Rss 增加 |
| `/usr/lib/libGLESv2.so.2.0` | 8/8/26/26 | 8.0 / 26.0 | 18.0 | 148.0 | 10.0 / 10.0 | a: Rss 增加 |
| `/usr/lib/libtvs-ht.so` | 15/15/33/33 | 15.0 / 33.0 | 18.0 | 108.0 | 6.0 / 6.0 | a: Rss 增加 |
| `/usr/lib/libci-api.so` | 15/15/30/30 | 15.0 / 30.0 | 15.0 | 188.0 | 12.0 / 12.0 | a: Rss 增加 |
| `/usr/lib/libbixby.so` | 2/2/14/14 | 2.0 / 14.0 | 12.0 | 48.0 | 5.0 / 5.0 | a: Rss 增加 |
| `/usr/lib/libbroadcastapp-util-core.so.0.1.0` | 13/13/25/25 | 13.0 / 25.0 | 12.0 | 100.0 | 6.0 / 7.0 | a: Rss 增加 |
| `/usr/lib/libvd-win-util.so.0.0.509` | 16/16/27/27 | 16.0 / 27.0 | 11.0 | 12.0 | 22.0 / 21.0 | b: 驻留近似不变、映射进程减少 |
| `/usr/lib/libmbr.so.0.1.0` | 22/22/31/31 | 22.0 / 31.0 | 9.0 | 104.0 | 15.0 / 15.0 | a: Rss 增加 |
| `/usr/lib/driver/libmali.so` | 333/347/347/347 | 340.0 / 347.0 | 7.0 | 0.0 | 7.0 / 7.0 | 未确定 |
| `/usr/lib/libitvs-hybrid-info.so.0.1.0` | 20/20/27/27 | 20.0 / 27.0 | 7.0 | 72.0 | 7.0 / 7.0 | a: Rss 增加 |
| `/usr/lib/libavoc.so` | 10/11/17/17 | 10.5 / 17.0 | 6.5 | 96.0 | 23.0 / 22.0 | a: Rss 增加 |
| `/usr/lib/libapp-core-ui-cpp.so.1.27.17` | 12/12/18/18 | 12.0 / 18.0 | 6.0 | 20.0 | 14.0 / 13.0 | a: Rss 增加 |

## 前 10 对象 ELF 体积与驻留

完整两侧 `.text`、LOAD、编译器信息和 readelf 状态在 [`top10_elf.tsv`](../data/tvs_daemon_code_pages/top10_elf.tsv)。缺失 ELF 时明确标为 MISSING；本次前 10 对象的两侧 ELF 均存在。

### tvs-daemon

| 对象 | .text GCC/LLVM KiB | r-x LOAD GCC/LLVM KiB | Rss GCC/LLVM KiB | 驻留比 GCC/LLVM | GCC LTO 痕迹 | LLVM clang | RPM |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/usr/lib/libtvs-api-native.so` | 878.8 / 596.8 | 1479.3 / 1464.9 | 600.0 / 1,052.0 | 40.6% / 71.8% | 无法判断（无 .symtab） | 是 | tvs-api-native-0.4.0-1.armv7l |
| `/usr/lib/libtvs-dvb-si.so` | 534.4 / 377.6 | 854.0 / 932.0 | 36.0 / 408.0 | 4.2% / 43.8% | 无法判断（无 .symtab） | 是 | tvs-dvb-si-0.1.1-1.armv7l |
| `/usr/lib/libtvs-iss.so` | 550.8 / 433.3 | 951.8 / 1104.0 | 412.0 / 764.0 | 43.3% / 69.2% | 无法判断（无 .symtab） | 是 | tvs-iss-0.3.1-1.armv7l |
| `/usr/lib/libtvs-util.so` | 491.1 / 390.2 | 899.7 / 1024.4 | 464.0 / 808.0 | 51.6% / 78.9% | 无法判断（无 .symtab） | 是 | tvs-util-0.1.1-1.armv7l |
| `/usr/lib/libtvs-dsm.so` | 582.1 / 494.0 | 1049.9 / 1091.3 | 56.0 / 380.0 | 5.3% / 34.8% | 无法判断（无 .symtab） | 是 | tvs-dsm-0.1.1-1.armv7l |
| `/usr/lib/libtvs-b2b.so` | 261.3 / 195.1 | 520.0 / 625.2 | 128.0 / 432.0 | 24.6% / 69.1% | 无法判断（无 .symtab） | 是 | tvs-b2b-0.0.1-1.armv7l |
| `/usr/lib/libgstreamer-1.0.so.0.2411.0` | 594.8 / 537.5 | 938.8 / 866.8 | 766.0 / 752.0 | 81.6% / 86.8% | 无法判断（无 .symtab） | 是 | gstreamer-1.24.11-2.armv7l |
| `/usr/lib/libtvs-dvbbase-scan.so` | 379.4 / 248.0 | 662.3 / 611.1 | 36.0 / 248.0 | 5.4% / 40.6% | 无法判断（无 .symtab） | 是 | tvs-dvbbase-scan-0.0.1-1.armv7l |
| `/usr/lib/libtvs-atsc30-parser.so` | 290.8 / 238.5 | 551.6 / 574.8 | 32.0 / 240.0 | 5.8% / 41.8% | 无法判断（无 .symtab） | 是 | tvs-atsc30-parser-0.1.1-1.armv7l |
| `/usr/lib/libtvs-ext.so` | 424.9 / 281.4 | 735.8 / 723.8 | 232.0 / 440.0 | 31.5% / 60.8% | 无法判断（无 .symtab） | 是 | tvs-ext-0.1.0-1.armv7l |

### tv-viewer

| 对象 | .text GCC/LLVM KiB | r-x LOAD GCC/LLVM KiB | Rss GCC/LLVM KiB | 驻留比 GCC/LLVM | GCC LTO 痕迹 | LLVM clang | RPM |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | 3927.0 / 4691.7 | 5586.4 / 6510.0 | 2,018.0 / 2,432.0 | 36.1% / 37.4% | 无法判断（无 .symtab） | 是 | org.tizen.tv-viewer-0.3.8-1.armv7l |
| `/usr/lib/libreminder-api.so.0.1.0` | 174.4 / 132.6 | 302.0 / 301.4 | 32.0 / 136.0 | 10.6% / 45.1% | 无法判断（无 .symtab） | 是 | reminder-api-0.2-1.armv7l |
| `/usr/lib/libtvs-parser.so` | 382.8 / 322.7 | 827.0 / 906.1 | 56.0 / 480.0 | 6.8% / 53.0% | 无法判断（无 .symtab） | 是 | tvs-parser-0.1.1-1.armv7l |
| `/usr/lib/libtv-viewer-kevent.so.0.1.0` | 52.0 / 43.8 | 84.8 / 124.2 | 40.0 / 84.0 | 47.2% / 67.7% | 无法判断（无 .symtab） | 是 | tv-viewer-kevent-0.2.1-1.armv7l |
| `/usr/lib/libtv-viewer-api.so.0.1.0` | 128.6 / 97.9 | 226.9 / 228.9 | 88.0 / 144.0 | 38.8% / 62.9% | 无法判断（无 .symtab） | 是 | tv-viewer-api-0.2.1-1.armv7l |
| `/usr/lib/libtvs-api.so` | 776.9 / 618.6 | 1349.4 / 1546.3 | 264.0 / 860.0 | 19.6% / 55.6% | 无法判断（无 .symtab） | 是 | tvs-api-0.5.18-1.armv7l |
| `/usr/lib/libbms-api.so` | 72.5 / 55.0 | 150.8 / 177.4 | 24.0 / 104.0 | 15.9% / 58.6% | 无法判断（无 .symtab） | 是 | bms-api-0.1.1-1.armv7l |
| `/usr/lib/libtvs-ht-api.so` | 163.9 / 113.0 | 293.2 / 340.6 | 80.0 / 216.0 | 27.3% / 63.4% | 无法判断（无 .symtab） | 是 | tvs-ht-0.1.1-1.armv7l |
| `/usr/lib/libflux-manager.so.0.1.0` | 448.5 / 396.9 | 706.3 / 658.1 | 92.0 / 172.0 | 13.0% / 26.1% | 无法判断（无 .symtab） | 是 | flux-manager-0.1-20190703.armv7l |
| `/usr/lib/libGLESv2.so.2.0` | 227.5 / 185.1 | 264.8 / 216.5 | 68.0 / 216.0 | 25.7% / 99.7% | 无法判断（无 .symtab） | 是 | coregl-0.2.0-0.armv7l |

## 驻留增加与共享分摊

观察分类规则：只对正的对象 ΔPss 计入 (a)/(b)；Rss “基本不变”的容差为 `max(16 KiB, GCC 平均 Rss 的 5%, GCC 两次 Rss 极差, LLVM 两次 Rss 极差)`。(a) 为 ΔRss 高于容差；(b) 为 |ΔRss| 不高于容差且完整快照中映射进程数下降。其余正值记“未确定”，负值单列抵消。这个规则用 Rss 与共享数识别模式，不能单凭汇总量证明逐页因果关系，尤其 (b) 的实际共享页集合仍可能不同。逐对象判别与容差在 [`object_classification.tsv`](../data/tvs_daemon_code_pages/object_classification.tsv)。

| 进程 | (a) Rss 增加 KiB | (b) 分摊模式 KiB | 未确定正差 KiB | 负向抵消 KiB | 对象净差 KiB |
| --- | --- | --- | --- | --- | --- |
| tvs-daemon | 5,446.0 | 351.5 | 99.0 | -128.0 | 5,768.5 |
| tv-viewer | 923.0 | 38.5 | 34.5 | -140.0 | 856.0 |

## 有数据支撑的结论与限制

- tvs-daemon 最大五项依次为 `libtvs-api-native.so` +452、`libtvs-dvb-si.so` +372、`libtvs-iss.so` +352、`libtvs-util.so` +344、`libtvs-dsm.so` +324 KiB；五项的 Rss 各自同量增加，且两侧映射进程数均为 1，属于 (a) 观察模式。GCC 板上这五个 ELF 都无 `.symtab`，按规定的痕迹规则无法判定是否做过 LTO。

- tvs-daemon 全部 r-x 对象正差中 (a) 合计 +5,446.0 KiB；(b) +351.5 KiB，其中 `libgstreamer-1.0.so.0.2411.0` +290.5 KiB（Rss −14 KiB，映射进程 6→5），是共享分摊模式，不能作为代码体积增长。其余正差 +99.0 KiB 未确定，负向抵消 −128.0 KiB。加总为对象净差 +5,768.5 KiB。

- 前五个对象 LLVM `.text` 均小于 GCC，但驻留 Rss/Pss 增加；已有数据能证明驻留变多，不能确定是代码路径、缓存状态、进程工作负载还是构建方式导致。前十对象的 GCC LTO 痕迹全部因 `.symtab` 缺失而无法判断；不能把 (a) 直接归因于 LTO。

- 两镜像服务集合和启动时点可能不同；这里只有同名同主程序的目标进程配对与两次快照，未对代码页的实际访问路径做追踪。

