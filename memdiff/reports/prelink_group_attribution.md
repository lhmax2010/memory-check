# 预链接实际覆盖分组：全系统 r-x Pss 对 Pss

## 样本、口径和可复核数据

本报告完全离线，未使用开发板或网络。当前 LLVM 样本为 2026-11-11 采集的 `T-KSU2EJAKUC-0101-PERF-202611061751`；GCC 为 2026-11-02 两次 `02_steady`。当前 LLVM 只采一次，因此跨镜像差值是 **LLVM 本次 − GCC 两次均值**，不是同镜像干预收益。当前板身份与采集质量见 [上一轮报告](system_code_page_sections.md) 和 [collection.json](../data/system_code_page_sections/collection.json)。

沿用上一轮 [file_residency.tsv](../data/system_code_page_sections/file_residency.tsv) 的 1,360 个 `eligible=True` 共同文件。本次 LLVM 逐文件 Pss 从 [vmas.tsv](../data/system_code_page_sections/vmas.tsv) 按同路径全部 r-xp 映射相加；GCC 两次逐映射 Pss 从 [原始 smaps](../data/gcc_baseline/boot1/memcheck/gcc_boot1_20261102_182343/02_steady/smaps_raw.txt.gz) 和 [boot2 smaps](../data/gcc_baseline/boot2/memcheck/gcc_boot2_20261102_192351/02_steady/smaps_raw.txt.gz) 流式重读，并逐文件断言与上一轮 `file_residency.tsv` 的 GCC 值一致。完整逐文件数值与分类理由在 [per_file.tsv](../data/prelink_group_attribution/per_file.tsv)，执行记录在 [run.log](../data/prelink_group_attribution/run.log)。单位以下均为 KiB；差值为 LLVM−GCC。

GCC 的进程主程序直接来自 smaps 的 `### PID comm exe` 头；LLVM 本次没有采 `/proc/PID/exe`，主程序以保存的 `maps` 中**最低地址 r-xp 文件映射**识别。每个 PID 的判定在 [process_main.tsv](../data/prelink_group_attribution/process_main.tsv)；这一规则无法证明进程没有在采集时更换主程序，因此涉及进程身份的乙/丙分组仍有该限制。

## 一、统一 Pss 口径与页并集差

1,360 个文件：LLVM Pss 和 **186,077.0**；GCC boot1/boot2 **177,070.0/172,715.0**，均值 **174,892.5**；Pss 对 Pss 差 **+11,184.5**。LLVM 文件偏移去重的唯一驻留为 191,844.0，比逐映射 Pss 和高 **5,767.0**。后一个差额是观测到的页并集与 Pss 和差；Pss 整数取整、文件页在未采到的进程中共享、采集非同时性均可贡献，不能仅凭现有数据全部定为取整。

| 当前 LLVM 映射进程数 | 文件数 | 唯一 r-x 驻留 | Pss 和 | 唯一 − Pss |
| --- | ---: | ---: | ---: | ---: |
| 1 | 687 | 105,620.0 | 105,616.0 | 4.0 |
| 2-9 | 347 | 40,700.0 | 39,623.0 | 1,077.0 |
| 10-49 | 223 | 32,012.0 | 29,794.0 | 2,218.0 |
| >=50 | 103 | 13,512.0 | 11,044.0 | 2,468.0 |

分档逐文件来源：[rounding_by_mapper_count.tsv](../data/prelink_group_attribution/rounding_by_mapper_count.tsv)。

## 二、按实际预链接覆盖分组

甲 = GCC 副本带 `GNU_LIBLIST` 的主程序；乙 = GCC 带任一预链接标记的库且 GCC 两次与当前 LLVM 的全部映射进程主程序都在这 10 个程序中；丙 = 带标记库但至少一个映射进程不在 10 个中；丁 = GCC 无标记的库；戊 = 其他可执行文件。“库/可执行文件”沿用 GCC [elf_stats.tsv](../data/gcc_baseline/elf/elf_stats.tsv) 的 `role`；标记来自 [elf_summary.tsv](../data/system_code_page_sections/elf_summary.tsv)。己为 GCC 与当前 LLVM ELF 副本按相同路径 SHA256 完全一致的覆盖组，会与甲到戊重复列示，不计入前五组合计。

| 组 | 文件 | LLVM Pss | GCC1 / GCC2 Pss | GCC 均值 | Pss 差 | LLVM 加载器节唯一 / 折算 Pss | GCC / LLVM 加载器节静态大小 | 加载器净增下界 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 甲 | 9 | 4,892.0 | 4,320.0 / 4,304.0 | 4,312.0 | 580.0 | 1,039.4 / 1,039.4 | 1,343.8 / 2,287.4 | -304.5 |
| 乙 | 62 | 12,570.0 | 7,212.0 / 7,132.0 | 7,172.0 | 5,398.0 | 7,004.2 / 7,002.7 | 4,481.2 / 7,084.2 | 3,702.1 |
| 丙 | 348 | 34,205.0 | 34,258.0 / 33,317.0 | 33,787.5 | 417.5 | 12,841.1 / 11,378.7 | 11,423.4 / 13,085.1 | -1,378.3 |
| 丁 | 857 | 110,595.0 | 107,087.0 / 103,958.0 | 105,522.5 | 5,072.5 | 37,750.7 / 37,363.6 | 34,039.1 / 41,204.9 | 3,008.2 |
| 戊 | 84 | 23,815.0 | 24,193.0 / 24,004.0 | 24,098.5 | -283.5 | 3,621.0 / 3,588.6 | 3,850.9 / 5,033.0 | -346.7 |
| 己 | 31 | 11,464.0 | 11,596.0 / 11,428.0 | 11,512.0 | -48.0 | 3,295.2 / 3,295.2 | 3,467.2 / 3,467.2 | -164.9 |

加载器节只含 `.dynsym/.dynstr/.gnu.hash/.hash/.gnu.version*/.rel.dyn/.rel.plt`；静态大小来自 [elf_sections.tsv](../data/system_code_page_sections/elf_sections.tsv)，驻留来自 [file_residency.tsv](../data/system_code_page_sections/file_residency.tsv)。LLVM 加载器节 Pss 按 `LLVM 节唯一驻留 / 文件唯一驻留 × 文件 Pss 和` 比例折算。“净增下界”逐文件采用 `max(0, LLVM 文件 Pss 和 − (唯一驻留 − 加载器节唯一驻留)) − min(GCC Pss 均值, GCC 加载器节静态大小)` 后求和。该式容许负值；它只约束本次观测的代码映射 Pss 差，不能保证关 PIE 或恢复预链接后获得相同收益。比例折算上界是任务规定的观测估计，也不是干预实验的严格上界。逐组未四舍五入结果见 [group_summary.tsv](../data/prelink_group_attribution/group_summary.tsv)。

GCC 的 10 个 `GNU_LIBLIST` 主程序及当前 LLVM ELF 验证：

| GCC 主程序 | 本次可信共同集 | 当前 LLVM ELF 类型 / DT_FLAGS_1 PIE |
| --- | --- | --- |
| `/usr/apps/boot-helper-dyboost-tv/bin/boot-helper-dyboost-tv` | 是 | ET_DYN / PIE |
| `/usr/apps/org.tizen.acm-service/bin/acm-service` | 否 | 未确定（当前 ELF 副本缺失） |
| `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | 是 | ET_DYN / PIE |
| `/usr/bin/amd` | 是 | ET_DYN / PIE |
| `/usr/bin/avocd` | 是 | ET_DYN / PIE |
| `/usr/bin/launchpad-loader` | 是 | ET_DYN / PIE |
| `/usr/bin/launchpad-process-pool` | 是 | ET_DYN / PIE |
| `/usr/bin/pulseaudio` | 是 | ET_DYN / PIE |
| `/usr/bin/rscmgr-service` | 是 | ET_DYN / PIE |
| `/usr/bin/tvs-daemon` | 是 | ET_DYN / PIE |

`acm-service` 未在当前板采集进程中运行，本次也没有拉回该可执行文件；因此只能确认**9/9 个可检查对象**为 ET_DYN 且带 PIE，不能声称 10/10。证据：[gnu_liblist_executables.tsv](../data/prelink_group_attribution/gnu_liblist_executables.tsv)。

## 三、不依赖 Pss 取整的机制指标

对每文件每次开机，在该文件所有映射进程中先将同进程的 r-x Rss 相加，再取最大值；它是该文件唯一驻留的下界。与该侧 ELF 加载器节静态大小比较，严格小于时计 1。原始值在 [per_file.tsv](../data/prelink_group_attribution/per_file.tsv)。

| 组 | GCC1 成立 | GCC2 成立 | LLVM 成立 |
| --- | ---: | ---: | ---: |
| 甲 | 0/9 (0.0%) | 0/9 (0.0%) | 0/9 (0.0%) |
| 乙 | 22/62 (35.5%) | 22/62 (35.5%) | 0/62 (0.0%) |
| 丙 | 0/348 (0.0%) | 0/348 (0.0%) | 1/348 (0.3%) |
| 丁 | 7/857 (0.8%) | 7/857 (0.8%) | 12/857 (1.4%) |
| 戊 | 0/84 (0.0%) | 1/84 (1.2%) | 0/84 (0.0%) |
| 己 | 1/31 (3.2%) | 1/31 (3.2%) | 1/31 (3.2%) |

乙组 GCC 仅 22/62（35.5%）成立，**不符合**“大多成立”的预期；LLVM 0/62 符合“几乎不成立”。丙、丁组两侧比例都很低。这里只如实记录结果，不把不符之处强行解释为某种加载器行为。

## 四、与周报程序清单逐项对账

周报 [第 56、68–84 行](weekly_data_table.md) 给出 **15 条完整路径**的 GCC 非 PIE 进程 rollup（Pss 与 Pss+SwapPss）；其 [第 87–101 行](weekly_data_table.md) 把同一 15 程序组用于 410 库私有脏页分组，但不重复逐路径列名。用户所称“14 个非 PIE 程序”和“15 个程序的私有脏页”并非周报中的两个逐字标题。14 条完整路径来自较早的 [tpms_memory_method.md 第 70–73 行](tpms_memory_method.md) 及 [process_comparison_by_executable.tsv](../data/static/process_comparison_by_executable.tsv) 的 14 条路径。两者相差 `acm-service`。按 `comm` 的 14 名称还存在 `launchpad-proce` 名称碰撞，故这里采用**完整路径**对账。完整列表和差集在 [program_list_comparison.json](../data/prelink_group_attribution/program_list_comparison.json)。

| GNU_LIBLIST 十程序 | 在早期 14 路径 | 在周报 15 路径 |
| --- | --- | --- |
| `/usr/apps/boot-helper-dyboost-tv/bin/boot-helper-dyboost-tv` | 是 | 是 |
| `/usr/apps/org.tizen.acm-service/bin/acm-service` | 否 | 是 |
| `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | 是 | 是 |
| `/usr/bin/amd` | 是 | 是 |
| `/usr/bin/avocd` | 是 | 是 |
| `/usr/bin/launchpad-loader` | 是 | 是 |
| `/usr/bin/launchpad-process-pool` | 是 | 是 |
| `/usr/bin/pulseaudio` | 是 | 是 |
| `/usr/bin/rscmgr-service` | 是 | 是 |
| `/usr/bin/tvs-daemon` | 是 | 是 |

10∩14 为 9 条；仅 10 中有 `/usr/apps/org.tizen.acm-service/bin/acm-service`。10∩15 为全部 10 条，15 中另外 5 条：

- `/usr/apps/com.samsung.tv.home-service/bin/com.samsung.tv.home-service`
- `/usr/bin/TAgentD`
- `/usr/bin/TIFSDaemon`
- `/usr/bin/app-defined-loader`
- `/usr/bin/tzdaemon`

## 五、甲乙两组代码段驻留量范围与噪声底

甲+乙的观测下界为 **3,397.6 KiB**；按任务指定比例折算的 LLVM 加载器节 Pss 上界估计为 **8,042.1 KiB**。这两个量是当前镜像对历史 GCC 的代码映射差额范围，**未确定**实际恢复预链接后的可回收量。甲组逐文件净增下界合计为负，不应截成零后再与乙组相加。

相同 SHA256 的己组 31 文件 Pss 差合计 **-48.0 KiB**；逐文件差值中位数 **0.0 KiB**、90 分位 **4.0 KiB**（线性插值）。逐文件分布见 [per_file.tsv](../data/prelink_group_attribution/per_file.tsv) 的 `same_sha256=1` 行。己组为同字节 ELF 的观测差，不可自动当作其他组的校正值。

本次只计 **r-xp 文件映射的 Pss**。周报 [第 87–103 行](weekly_data_table.md) 的 410 库 `r-- + rw-` 文件映射 Private_Dirty 差为 **13.923828 MiB**；权限集合互斥，故同一映射页不会同时落入本次 r-x 与该私有脏页池。Pss 与 Private_Dirty 也不是可直接相加的同一指标，不能把两个观测差简单相加称作总收益。

## 不确定与复核边界

- 当前 LLVM 比第三轮 LLVM 更新；GCC 两次与本次 LLVM 的服务集合、采集时刻不同，跨镜像差值不能单独定因。
- 当前 `acm-service` 的 ELF 副本缺失，10 程序的当前 PIE 状态只验证了 9 个。
- LLVM 进程主程序依据 maps 最低地址映射识别；缺少同次 `/proc/PID/exe` 核验。
- 6 个采集时退出的 PID 和上一轮排除的 114 个共同文件仍不在可信集合中。
