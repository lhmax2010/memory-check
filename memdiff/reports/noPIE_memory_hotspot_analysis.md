# noPIE 新镜像剩余内存开销：固定 94 身份的离线定位

## 结论与边界

六次快照和固定 94 个 `(comm, exe)` 身份完全沿用 [整体差值核对](noPIE_memory_delta_reconciliation.md) 的输入与规则。本轮每次仅汇总已成功读取的 94 个进程；所有值为逐映射 **Pss+SwapPss，单位 KiB**。相对 GCC，C 均值仍减少 20,183 KiB；相对第三轮 LLVM 减少 26,145 KiB。以下正增量是下降总量内部的抵消项，不能互相相加为可回收量。两次启动仅用于观察区间是否分离，不作统计显著性判断。新镜像同时改变 noPIE、LTO、MLGO 等条件，单项因果未确定。

六次输入的 SHA256 在运行时与 [上一轮输入清单](../data/noPIE_memory_delta_reconciliation/inputs.tsv) 逐项核对；本轮 [数据](../data/noPIE_memory_hotspot_analysis/validation.json) 记录 manifest 和固定清单哈希。旧 LLVM 对照是第三轮两次开机，没有混入 11 月 11 日单次数据。noPIE BUILD_ID 为 `T-KSU2EJAKUC-0101-PERF-202611120549`。原始快照、boot ID、采样时间和稳定标记见[输入 manifest](../data/noPIE_memory_delta_reconciliation/input_manifest.json) 与[原报告](noPIE_memory_delta_reconciliation.md)。

### 分类定义

- `file_exec`：文件路径且映射权限含 `x`；`file_readonly`：文件路径、无 `x`、有 `r`、无 `w`；`file_writable`：文件路径且有 `w`。其余文件映射保留 `file_other`。不跨镜像按虚拟地址配对。
- `stack` 只认明确的 `[stack]`/`[stack:<tid>]` 等标签；`[heap]`、`[anon]`、`[anon:...]` 和无路径映射归 `anonymous`。未标注 worker 栈无法识别，仍留在匿名类。
- `/dev/`、`/proc/`、`/sys/`、`/kdbus-`、memfd 和其他内核特殊标签归 `special`；路径带 `(deleted)` 保留字面值，绝不与未删除路径合并。每条 VMA 恰好进入一个主类。Private_Dirty、Rss、Shared_Clean 只作辅助诊断，不加入 Pss+SwapPss 总和。

## 六次 C 总量及映射主类

| 快照 | 身份实例 | Pss | SwapPss | 合计 | 文件执行 | 文件只读 | 文件可写 | 文件其他 | 可识别栈 | 其他匿名 | 特殊映射 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GCC1 | 94 | 413,357 | 101,952 | 515,309 | 178,402 | 92,777 | 68,589 | 0 | 30,865 | 141,372 | 3,304 |
| GCC2 | 94 | 387,026 | 115,820 | 502,846 | 171,751 | 90,734 | 67,785 | 0 | 29,421 | 131,833 | 11,322 |
| LLVM31 | 94 | 402,594 | 115,980 | 518,574 | 178,420 | 106,824 | 65,457 | 0 | 24,335 | 132,918 | 10,620 |
| LLVM32 | 94 | 395,105 | 116,400 | 511,505 | 178,465 | 106,845 | 65,463 | 0 | 25,983 | 132,040 | 2,709 |
| noPIE1 | 94 | 370,577 | 118,800 | 489,377 | 161,660 | 94,647 | 64,359 | 0 | 27,705 | 129,696 | 11,310 |
| noPIE2 | 94 | 370,408 | 118,004 | 488,412 | 161,758 | 94,649 | 64,347 | 0 | 27,741 | 128,621 | 11,296 |

逐进程六次值及各类别见 [数据](../data/noPIE_memory_hotspot_analysis/C_processes_six.tsv)；逐 VMA 分类见 [数据](../data/noPIE_memory_hotspot_analysis/classified_vmas.tsv.gz)。

## A. 正增量进程与文件

表内新旧两次值按同一镜像并列；均值差是新镜像均值减基线均值，区间分离表示两次新值均高于两次旧值。文件级 0 表示在对应完整 C 快照未映射，不表示文件不存在；`*_present` 列保留这一区别。完整正负进程与文件差分见 [数据](../data/noPIE_memory_hotspot_analysis/C_process_comparisons.tsv)、[数据](../data/noPIE_memory_hotspot_analysis/C_file_comparisons.tsv)，前 20 正项另见 [数据](../data/noPIE_memory_hotspot_analysis/top20_process_positive.tsv)、[数据](../data/noPIE_memory_hotspot_analysis/top20_file_positive.tsv)。

### noPIE − GCC：正增量进程

| 身份 | 旧 1/2 | 新 1/2 | Δ合计 | ΔPss/Swap | 区间 | 主要类别净变化 |
| --- | --- | --- | --- | --- | --- | --- |
| enlightenment \| /usr/bin/enlightenment | 17,327/23,495 | 22,814/22,793 | 2,392.5 | 1,372.5/1,020 | overlap | 特殊映射 4,050, 文件执行 -1,596.5, 可识别栈 -178, 其他匿名 98, 文件只读 84, 文件可写 -65 |
| TA_native-home \| /usr/bin/team-launcher | 41,422/45,011 | 44,658/44,426 | 1,325.5 | 1,325.5/0 | overlap | 文件执行 1,349, 可识别栈 -436, 文件只读 241, 其他匿名 222, 文件可写 -52 |
| launchpad-loade \| /usr/bin/launchpad-loader | 7,343/7,381 | 7,778/7,774 | 414 | 290/124 | separated_up | 文件只读 229, 其他匿名 128, 文件执行 63.5 |
| cynara \| /usr/bin/cynara | 3,811/4,387 | 4,405/4,409 | 308 | 324/-16 | separated_up | 其他匿名 262, 文件执行 50 |
| pisa-service \| /opt/usr/apps/com.samsung.tv.pisa-service/bin/pisa-service | 3,158/3,430 | 3,561/3,552 | 262.5 | 400.5/-138 | separated_up | 文件执行 220.5, 可识别栈 70, 文件可写 -64, 其他匿名 58 |
| avocd \| /usr/bin/avocd | 7,062/7,057 | 7,311/7,326 | 259 | -83/342 | separated_up | 文件执行 268.5, 文件可写 -40 |
| connectivity-co \| /usr/bin/connectivity-common-daemon | 8,405/8,423 | 8,648/8,642 | 231 | -147/378 | separated_up | 文件执行 194.5, 文件只读 80.5, 文件可写 -40 |
| sdbd \| /usr/sbin/sdbd | 2,722/2,985 | 3,180/2,887 | 180 | 162/18 | overlap | 其他匿名 206 |
| tv-viewer \| /usr/apps/org.tizen.tv-viewer/bin/tv-viewer | 12,689/12,707 | 12,864/12,845 | 156.5 | 56.5/100 | separated_up | 文件只读 193, 其他匿名 -132, 可识别栈 126, 文件可写 -75, 文件执行 44 |
| app-defined-loa \| /usr/bin/app-defined-loader | 1,940/1,941 | 2,059/2,058 | 118 | 198/-80 | separated_up | 文件只读 207, 文件可写 -84 |

### noPIE − GCC：正增量文件（仅 C 内映射）

| 文件路径 | 旧 1/2 | 新 1/2 | Δ合计 | ΔPss/Swap | 区间 | C 使用者 | 主要映射变化 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| /usr/lib/libvorbisenc.so.2.0.12 | 0/0 | 819/819 | 819 | 755/64 | separated_up | 0/0→19/19 | 文件只读 728, 文件可写 76 |
| /usr/share/elementary/themes/vd-efl-theme-tizen.edj | 0/13 | 561/561 | 554.5 | 554.5/0 | separated_up | 5/5→5/5 | 文件只读 554.5 |
| /usr/lib/libpisa-ipc.so | 1,003/1,001 | 1,460/1,460 | 458 | 454/4 | separated_up | 5/5→5/5 | 文件执行 458 |
| /opt/usr/apps/com.samsung.tv.ContentsBrowser/shared/res/libcompcb.so | 1,372/1,372 | 1,732/1,732 | 360 | 360/0 | separated_up | 1/1→1/1 | 文件执行 376 |
| /usr/bin/avocd | 924/916 | 1,232/1,232 | 312 | 314/-2 | separated_up | 1/1→1/1 | 文件执行 314 |
| /usr/lib/libgstreamer-1.0.so.0.2411.0 | 531/530 | 838/838 | 307.5 | 305.5/2 | separated_up | 5/5→5/5 | 文件执行 307.5 |
| /usr/share/connectivity-common-daemon/plugins/libbtapp-lite.so | 1,740/1,740 | 2,020/2,020 | 280 | 274/6 | separated_up | 1/1→1/1 | 文件执行 280 |
| /usr/lib/libgobject-2.0.so.0.8000.5 | 758/754 | 998/995 | 240.5 | 184.5/56 | separated_up | 84/84→84/84 | 文件只读 249 |
| /usr/lib/librpc-port.so.1.21.18 | 713/705 | 908/908 | 199 | 17/182 | separated_up | 57/57→57/57 | 文件可写 228 |
| /usr/apps/org.tizen.tv-viewer/bin/tv-viewer | 2,036/2,024 | 2,228/2,228 | 198 | 198/0 | separated_up | 1/1→1/1 | 文件执行 198 |

### noPIE − LLVM3：正增量进程

| 身份 | 旧 1/2 | 新 1/2 | Δ合计 | ΔPss/Swap | 区间 | 主要类别净变化 |
| --- | --- | --- | --- | --- | --- | --- |
| enlightenment \| /usr/bin/enlightenment | 23,066/14,994 | 22,814/22,793 | 3,773.5 | 3,185.5/588 | overlap | 特殊映射 4,050, 文件执行 -230.5, 可识别栈 -188, 其他匿名 162 |
| smartthings-thi \| /opt/usr/apps/com.samsung.tizen.smartthings-thing/bin/smartthings-thing | 5,126/5,136 | 5,095/5,394 | 113.5 | -194.5/308 | overlap | 文件执行 69 |
| sdbd \| /usr/sbin/sdbd | 2,950/2,926 | 3,180/2,887 | 95.5 | 101.5/-6 | overlap | 其他匿名 94 |
| psa-init \| /usr/bin/psa-init | 4,073/4,042 | 4,106/4,125 | 58 | -24/82 | separated_up | 文件执行 74 |
| allshare-svc \| /usr/bin/allshare-svc | 2,831/2,845 | 2,873/2,855 | 26 | -8/34 | separated_up | 各类均 <40 |
| fconfigd \| /usr/bin/fconfigd | 1,506/1,510 | 1,514/1,514 | 6 | 4/2 | separated_up | 各类均 <40 |
| wpa_supplicant \| /usr/sbin/wpa_supplicant | 2,064/2,063 | 2,069/2,068 | 5 | 5/0 | separated_up | 各类均 <40 |
| license-manager \| /usr/bin/license-manager-agent | 568/568 | 572/572 | 4 | 0/4 | separated_up | 各类均 <40 |
| zone-init \| /usr/bin/zone-init | 70/70 | 74/74 | 4 | 0/4 | separated_up | 各类均 <40 |
| kfactoryd \| /prd/usr/bin/kfactoryd | 460/460 | 463/463 | 3 | -1/4 | separated_up | 各类均 <40 |

### noPIE − LLVM3：正增量文件（仅 C 内映射）

| 文件路径 | 旧 1/2 | 新 1/2 | Δ合计 | ΔPss/Swap | 区间 | C 使用者 | 主要映射变化 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| /usr/lib/libsecurity-manager-commons.so.1.0.2 | 1,447/1,447 | 1,671/1,671 | 224 | -4/228 | separated_up | 61/61→61/61 | 文件可写 244 |
| /usr/apps/org.tizen.webappservice/bin/webappservice | 916/920 | 1,020/1,020 | 102 | 102/0 | separated_up | 1/1→1/1 | 文件执行 102 |
| /usr/bin/avocd | 1,152/1,152 | 1,232/1,232 | 80 | 80/0 | separated_up | 1/1→1/1 | 文件执行 144, 文件只读 -64 |
| /opt/usr/apps/Ddrm/fkp/lib/libfkpCore.so | 516/496 | 584/584 | 78 | 78/0 | separated_up | 1/1→1/1 | 文件执行 78 |
| /usr/lib/libbluetooth-api.so.1.0.0 | 512/514 | 590/576 | 70 | 6/64 | separated_up | 21/21→21/21 | 文件可写 68 |
| /usr/lib/libslive-provider.so.0.1 | 312/312 | 369/369 | 57 | 11/46 | separated_up | 16/16→16/16 | 文件可写 64 |
| /usr/share/dotnet.tizen/tvappapi/Tizen.TV.Service.CoBA.Common.ni.dll | 136/136 | 180/180 | 44 | 44/0 | separated_up | 1/1→1/1 | 文件只读 52 |
| /usr/lib/libdali2-toolkit.so.2.0.0 | 691/691 | 733/735 | 43 | 43/0 | separated_up | 1/1→1/1 | 文件执行 44 |
| /usr/apps/com.samsung.tv.native-home/lib/libnative-api-devgru-vivframework.so.2.0.0 | 580/580 | 620/620 | 40 | 40/0 | separated_up | 1/1→1/1 | 文件执行 40 |
| /opt/usr/apps/com.samsung.tizen.smartthings-thing/lib/liboctbstack.so | 532/532 | 532/608 | 38 | 38/0 | overlap | 1/1→1/1 | 各类均 <40 |

### 重点对象的证据解释

1. **`enlightenment`** 相对 LLVM3 为 +3,773.5 KiB，但观察区间重叠。其特殊映射净增 +4,050 KiB，来自 `/dev/dri/card0`：LLVM3 两次为 8,100/0 KiB，noPIE 为 8,100/8,100 KiB。同一对象的文件执行映射反而 −230.5 KiB；noPIE `.text` 为 1,022,500 B，LLVM3 为 1,029,676 B。这首先是 GPU 映射/状态可比性问题，不能称作代码增长。[数据](../data/noPIE_memory_hotspot_analysis/classified_vmas.tsv.gz)、[数据](../data/noPIE_memory_hotspot_analysis/static_elf_evidence.tsv)。
2. **`libpisa-ipc.so`** 的 C 内文件 Pss+SwapPss 相对 GCC 为 +458 KiB，5/5 与 5/5 个 C 身份映射，全部来自执行映射；GCC/noPIE `.text` 为 479,996/885,568 B。静态大小变化与映射增量同向，但版本/源码/编译参数尚未配齐，不能直接归因 LTO 或编译器。[数据](../data/noPIE_memory_hotspot_analysis/C_file_comparisons.tsv)、[数据](../data/noPIE_memory_hotspot_analysis/static_elf_evidence.tsv)。
3. **`libvorbisenc.so.2.0.12`** 相对 GCC 为 +819 KiB，其中文件只读 +728 KiB；GCC 两次固定 C 均未映射该路径，因此从映射文件拉回的 GCC ELF 副本也未取得，无法核对静态版本。这首先是加载/依赖集合差异，不是同一文件的内存增长。LLVM3 与 noPIE 均有 ELF 副本，noPIE 相对 LLVM3 实际 −186 KiB。[数据](../data/noPIE_memory_hotspot_analysis/C_file_comparisons.tsv)、[数据](../data/noPIE_memory_hotspot_analysis/static_elf_evidence.tsv)。
4. **`avocd`** 相对 GCC 进程合计 +259 KiB，其中 Pss −83、SwapPss +342；自身文件 +312 KiB，其执行映射 +314 KiB。GCC/noPIE `.text` 为 662,936/1,276,590 B，静态差距明显，但进程合计受其他映射和换出抵消。[数据](../data/noPIE_memory_hotspot_analysis/C_process_comparisons.tsv)、[数据](../data/noPIE_memory_hotspot_analysis/static_elf_evidence.tsv)。
5. **`TA_native-home` / `team-launcher`** 相对 GCC 进程 +1,325.5 KiB，但区间重叠；文件执行映射 +1,349 KiB、可识别栈 −436 KiB。主程序 `.text` noPIE 仅 572 B，因此不能把 +1,349 KiB 归到主程序代码；需先拆其加载文件和同场景工作量。[数据](../data/noPIE_memory_hotspot_analysis/C_process_comparisons.tsv)、[数据](../data/noPIE_memory_hotspot_analysis/static_elf_evidence.tsv)。

### 前 10 个 ELF 的静态核查

按每个对象在进程或文件视角的**较大正差值**排序选 10 个，不把两种视角相加。原始平台交叉 readelf 节表、程序头、动态段和 note 已压缩保存在数据目录；工具路径和 SHA256 见 [数据](../data/noPIE_memory_hotspot_analysis/static_tool.json)。下表 `.text` 为文件节大小（B），不是驻留 Pss。缺副本写未取得，不解释为映射值 0。

| 序 | 路径 | GCC ELF/.text/Build ID 前缀 | LLVM3 | noPIE | 原 410 库 |
| --- | --- | --- | --- | --- | --- |
| 1 | /usr/bin/enlightenment | DYN; .text 1114784; a15d853be5 | DYN; .text 1029676; a19bd341fa | DYN; .text 1022500; e83aa4da07 | 0 |
| 2 | /usr/bin/team-launcher | DYN; .text 656; fd7eaf5d99 | DYN; .text 596; 735458ec8c | DYN; .text 572; e6baa7824a | 0 |
| 3 | /usr/lib/libvorbisenc.so.2.0.12 | 未取得 | DYN; .text 6496; 659fec6399 | DYN; .text 6496; 53445222a8 | 0 |
| 4 | /usr/lib/libpisa-ipc.so | DYN; .text 479996; 9e02466071 | DYN; .text 885568; 6fbf2d1438 | DYN; .text 885568; 0258dbf8ea | 0 |
| 5 | /usr/bin/launchpad-loader | EXEC; .text 7952; fbd1d3fe02 | DYN; .text 7050; 0d7e6da075 | EXEC; .text 7006; 39433ec05d | 0 |
| 6 | /opt/usr/apps/com.samsung.tv.ContentsBrowser/shared/res/libcompcb.so | DYN; .text 1975260; 8b489faf53 | DYN; .text 2752080; 93d76eecfe | DYN; .text 2752080; 63bf8f0d40 | 0 |
| 7 | /usr/bin/avocd | EXEC; .text 662936; db4d269c2b | DYN; .text 1274276; 678c9b8c84 | EXEC; .text 1276590; 495e15b364 | 0 |
| 8 | /usr/bin/cynara | DYN; .text 88296; 5e9704a27b | DYN; .text 113306; 96b30924f1 | DYN; .text 106388; a0bb5e18e6 | 0 |
| 9 | /usr/lib/libgstreamer-1.0.so.0.2411.0 | DYN; .text 609088; 50b90dd7f7 | DYN; .text 550440; e20079df5d | DYN; .text 550440; c17051d057 | 1 |
| 10 | /usr/share/connectivity-common-daemon/plugins/libbtapp-lite.so | DYN; .text 1917612; dd520bf5fa | DYN; .text 1934712; f4bd445da0 | DYN; .text 1939392; f017a27a9e | 0 |

同路径三侧哈希和 Build ID 多数不同，只能证明副本字节不相同；没有对应包版本和同源码构建记录时，“同版本”与“编译器造成”均未确定。`.comment` 为局部编译痕迹，不能覆盖整个包。PT_LOAD 权限、文件/内存大小与对齐、`.rodata/.dynsym/.dynstr` 和重定位节大小详见 [数据](../data/noPIE_memory_hotspot_analysis/static_elf_evidence.tsv)。本轮没有逐页节归属数据，不能把 r-x Pss 精确分给 `.text` 或 `.dynsym`。

## B. argot 路径族的可比性

新镜像两次都测到三条路径；GCC 和 LLVM3 四次旧快照的**已测台账**均无同身份记录，但这不能证明旧镜像从未安装/启动，也不能给出三者的同程序增长率。noPIE 两次各有 6 个采集中退出、未获得完整身份和内存的 PID，未测部分未估算。同次 `/proc/<pid>/status` 的 PPid 证明两次均有 `systemd→tsr→tsr-bwrap→tsr→argot` 链；这是父子关系事实，是否属于测试污染/预期业务仍未确定。[数据](../data/noPIE_memory_hotspot_analysis/argot_capture_audit.tsv)。

| 路径 | 新实例 1/2 | Pss 1/2 | Swap 1/2 | 合计 1/2 | 可比性 |
| --- | --- | --- | --- | --- | --- |
| /opt/usr/share/argot/.local/bin/tsr | 2/2 | 628/612 | 340/356 | 968/968 | 旧四次不在已测台账；同程序比较不可用 |
| /opt/usr/share/argot/.local/bin/tsr-bwrap | 1/1 | 96/96 | 68/68 | 164/164 | 旧四次不在已测台账；同程序比较不可用 |
| /usr/apps/com.samsung.tizen.argot/bin/argot | 1/1 | 8536/8576 | 3504/3436 | 12040/12012 | 旧四次不在已测台账；同程序比较不可用 |

三者在 noPIE 第一次合计 **13,172 KiB**、第二次 **13,144 KiB**；上一轮报告的 13,158 KiB 是两次均值：`argot` 12,026 + `tsr` 968 + `tsr-bwrap` 164。这解释了 R 净差 +13,364 KiB 的 98.46%，但只是一侧测得的进程集合/运行状态贡献，**不是同程序内存回退**。当前 `argot` 可执行副本 `.comment` 含 Tizen GCC、Ubuntu GCC 与 rustc 1.94.0 标记，其 10,059,108 B `.text` 和相关静态节见 [数据](../data/noPIE_memory_hotspot_analysis/static_elf_evidence.tsv)；这不足以推断包是否完整迁移到 clang、是否使用 LTO，旧两镜像没有可配对副本。

三者均归“**当前高占用但历史不可比；需要服务/镜像配置证据**”。现有父子链支持它们作为同一运行树，不支持将三者每项视为独立优化收益。未来先核对镜像包清单、启动单元/工作负载与采样时刻，再决定是否进入同程序优化实验。

## 候选清单与最小验证

下列排序综合正增量、两次区间、同对象可比性和可验证性；“验证”不代表本轮实施，也不承诺节省量。进程与其映射文件会重叠，候选增量不得累加。完整候选字段见 [数据](../data/noPIE_memory_hotspot_analysis/candidates.tsv)。

| 优先级 | 对象 | 对照 | 旧 1/2 | 新 1/2 | 均值差 | 区间 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | /usr/lib/libpisa-ipc.so | GCC | 1003/1001 | 1460/1460 | 458 | separated_up | 先核实同源码包/版本与构建参数，再在同版本受控构建中量 .text 与 r-x Pss |
| P1 | enlightenment \| /usr/bin/enlightenment | LLVM3 | 23066/14994 | 22814/22793 | 3773.5 | overlap | 先在同 GPU 状态、同 uptime 下复测 /dev/dri/card0 Pss，区分 0/8100 KiB 状态 |
| P1 | argot+tsr+tsr-bwrap | LLVM3 | not_measured/not_measured | 13172/13144 | not_comparable | insufficient | 先核对三版包/服务启用与父子链、相同工作负载；再决定是否比较同程序 |
| P2 | /usr/lib/libvorbisenc.so.2.0.12 | GCC | 0/0 | 819/819 | 819 | separated_up | 先核对 GCC 未在固定 C 映射的原因与两侧依赖集合；另找 GCC 包版本 |
| P2 | /usr/bin/avocd | GCC | 924/916 | 1232/1232 | 312 | separated_up | 核对同源码/版本与 ELF 配置，复测 r-x Pss 和 SwapPss；再考虑构建实验 |
| P2 | launchpad-loade \| /usr/bin/launchpad-loader | GCC | 7343/7381 | 7778/7774 | 414 | separated_up | 核对两次依赖集合、文件只读页和匿名分配；同负载复测 |
| P3 | TA_native-home \| /usr/bin/team-launcher | GCC | 41422/45011 | 44658/44426 | 1325.5 | overlap | 固定启动场景与线程数，逐文件核对执行映射及栈变化 |
| P3 | /opt/usr/apps/com.samsung.tv.ContentsBrowser/shared/res/libcompcb.so | GCC | 1372/1372 | 1732/1732 | 360 | separated_up | 核对同源码包/版本与构建选项，复测该文件的 r-x Pss |
| P3 | /usr/lib/libsecurity-manager-commons.so.1.0.2 | LLVM3 | 1447/1447 | 1671/1671 | 224 | separated_up | 同 uptime 复测该文件 SwapPss、进程数和可写映射；先排除换出状态 |

## 校验、覆盖和需要修正的表述

所有 6 次固定 94 身份 C 与上一轮 `six_snapshots.tsv` **逐次 0 KiB 差**；逐进程主类之和、94 身份合计、文件映射总和对文件主类之和均为 **0 KiB 误差**。从身份差分重算 ΔC：noPIE−GCC −20,183 KiB，noPIE−LLVM3 −26,145 KiB，与 [上一轮比较表](../data/noPIE_memory_delta_reconciliation/comparisons.tsv) 相同。实际分类 VMA 299,905 条，其中固定 C 298,788 条、argot 路径族 1,117 条；六次共 564 个固定 C 进程实例。[数据](../data/noPIE_memory_hotspot_analysis/validation.json)。

本轮仅对固定 C 和 argot 三路径族逐 VMA 重读；不声称覆盖 T 中其他 R 的映射。noPIE 两次各 6 个采集时退出/不完整 PID 无法计入已采集总量；旧镜像约 45 分钟采样而新镜像约 13 分钟，GPU、Swap 和应用工作量可能变化。文件级按路径配对，不把不同路径/版本自动认作同一二进制。同一快照同路径的文件映射还核对 device/inode；若出现多个 inode，脚本停止，不静默合并。GCC 的 `libvorbisenc` 文件副本未取得；多处包版本/同源码记录缺失。脚本不读终端输入，运行日志与结束状态见 [数据](../data/noPIE_memory_hotspot_analysis/run_console.log)、[数据](../data/noPIE_memory_hotspot_analysis/static_console.log)。

旧报告数值无需更正；需要避免把 `argot` 路径族 +13,158 KiB 表述为“同程序回退”或“新服务已证实”，以及把 `enlightenment` 的 GPU 特殊映射差额表述为 `.text` 增长。

## 复现

```bash
ulimit -v 2500000
taskset -c 0 nice -n 19 ionice -c3 python3 memdiff/scripts/nopie_memory_hotspots.py --manifest memdiff/data/noPIE_memory_delta_reconciliation/input_manifest.json --out memdiff/data/noPIE_memory_hotspot_analysis
taskset -c 0 nice -n 19 ionice -c3 python3 memdiff/scripts/nopie_hotspot_static.py --out memdiff/data/noPIE_memory_hotspot_analysis
taskset -c 0 nice -n 19 ionice -c3 python3 memdiff/scripts/nopie_hotspot_report.py --out memdiff/data/noPIE_memory_hotspot_analysis --report memdiff/reports/noPIE_memory_hotspot_analysis.md
taskset -c 0 nice -n 19 ionice -c3 python3 -m unittest memdiff.tests.test_nopie_memory_hotspots
```
