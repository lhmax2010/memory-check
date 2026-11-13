# noPIE LLVM 镜像：恢复预链接的静态状态与内存观测（第一部分）

采集日期 2026-11-13，板子 `192.168.108.26`，`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611120549`。本报告只完成任务的**第一部分**；未撤销任何库的预链接。差值均为新镜像减旧镜像，单位 KiB，且是**跨镜像观测差**，不能单独归因为预链接。新镜像同时改变了 LTO、MLGO、PIE 默认值和服务集合。原始采集在 [`boots/`](../data/noPIE_prelink_validation/boots/)，两次 `collect.py` 和 `budget.py` 均成功结束。用于汇总的中间表是 [`three_image_comparison.tsv`](../data/noPIE_prelink_validation/three_image_comparison.tsv)、[`first_part_summary.json`](../data/noPIE_prelink_validation/first_part_summary.json)。

## 身份、采集质量与静态预链接状态

两次冷启动的 boot ID 为 `48c5ccb1-cd54-4b94-b518-2486cf0a0d42`、`2cf21223-81d9-4623-81da-c556dcf62577`；每次均核对 `armv7l`、`NT72671D`、cmdline `KSU2E` 和相同 BUILD_ID。内核为 clang 22.1.8、LLD 22.1.8 编译。开机后 823/799 秒满足 `collect.py` 的稳定条件；完整进程 315/314，采集期间退出或不完整进程各 6；拉回 1,384/1,385 个 ELF，均与板上 SHA256 相同。每次收尾 `sdb root off` 后 UID 回到 5001，boot ID 未变。证据：[`boot1/collection/collection.json`](../data/noPIE_prelink_validation/boots/boot1/collection/collection.json)、[`boot2/collection/collection.json`](../data/noPIE_prelink_validation/boots/boot2/collection/collection.json)、各自 `collect.log` 和预算 `progress.log`。普通 `systemctl reboot` 虽返回 0 却未换 boot ID；实际两次冷启动先 `sync` 再以 root 调用 `/sbin/reboot -f`，均以 boot ID 变化为成功门禁。

19 个目标**均存在且为 ET_EXEC**；其中 **18 个**同时带 `GNU_LIBLIST` 与 `.gnu.prelink_undo`，唯一例外为 `/usr/bin/TIFSDaemon`（两者均无），所以 TIFSDaemon 未预链接成功。19 个文件的 `.comment` 都同时含 Tizen GCC 14.2.0 与 clang 22.1.8 字符串；该节不能证明每个源文件的编译器。逐目标的路径、类型、标记、注释及板上/主机同 SHA 见 [`targets19.tsv`](../data/noPIE_prelink_validation/targets19.tsv)，原始交叉 readelf 为 `probe_raw/readelf_0001.stdout` 到 `readelf_0019.stdout`；TIFSDaemon 是第 2 个。目标清单沿用 [`prelink_tool_validation.md`](prelink_tool_validation.md)。

8 个 `/etc/prelink.conf` 目录用包含去重的文件名扫描取得 419 个 `.gnu.prelink_undo` 字节串候选；逐个拉回并由指定交叉 readelf 核对后，**418 个库**同时带 `.gnu.prelink_undo` 和 `GNU_PRELINKED`，另一个为无标记的误命中。数量与旧 GCC 出厂态 418 个带标记库相同（[`prelink_undo_ab.md`](prelink_undo_ab.md)“准备与门禁”）。新镜像逐文件结果、SHA、readelf 返回码见 [`probe_result.json`](../data/noPIE_prelink_validation/probe_result.json)，原始扫描见 `probe_raw/candidate_scan.stdout`。该扫描以 `.gnu.prelink_undo` 字节串为候选入口；若存在**只有动态项而没有该节**、且未被两次映射 ELF 拉取覆盖的文件，本轮无法排除漏计，所以 418 是已确认数。

两次快照中已映射 ELF 分别为 1,384/1,385 个；ET_EXEC 各 14 个、带 PIE 标记的 ET_DYN 为 87/86 个。11-11 LLVM 的已映射 PIE 为 103 个，见 [`llvm_memory_budget.md`](llvm_memory_budget.md) 和重算的 [`elf_metrics.tsv`](../data/noPIE_prelink_validation/llvm1111_budget/elf_metrics.tsv)；各镜像进程和映射文件集合不同，不能把 103−87 全算作关闭 PIE 的文件数。周报所用 GCC 非 PIE **15 条路径**在本镜像全部为 ET_EXEC：14 个见两次 [`elf_metrics.tsv`](../data/noPIE_prelink_validation/boots/boot1/budget/elf_metrics.tsv)，未运行的 `acm-service` 见 `targets19.tsv`；清单来源 [`classification.json`](../data/llvm_round3/analysis/classification.json)。

## 健康检查和预链接诊断

两次内存快照中，要求的十个程序有 **9/10** 在运行；`acm-service` 两次都未出现，尽管其可执行文件存在且带整程序预链接标记。其余九项按 `/proc/PID/exe` 路径核对，考虑了 `launchpad-loade`、`launchpad-proce`、`boot-helper-dyb` 的进程名截断。依据：两份 [`process_budget.tsv`](../data/noPIE_prelink_validation/boots/boot1/budget/process_budget.tsv)、[`boot2 对应表`](../data/noPIE_prelink_validation/boots/boot2/budget/process_budget.tsv)。本轮未拉起该服务，健康门禁“十个都在运行”**未通过**；涉及服务集合的内存差不能归因预链接。

当前 boot2 的 `systemctl --failed` 列出 6 个单元：`com.samsung.tv.qse-daemon.service`、`kzram.service`、`org.tizen.mbr-daemon.service`、`security-emdaemon.service`、`ses-usb-installer@sda1.service`、`vdca-update.service`。11-11 LLVM 没有同项原始清单，**无法判定是否新增**。`/opt/usr/share/crash`、`/opt/share/crash/dump`、`/opt/share/crash` 当前查询到 0 个常规文件；11-11 的同目录基线未保存，所以“新增 coredump 数”**未确定**，当前观测数为 0。证据：[`failed_units.stdout`](../data/noPIE_prelink_validation/probe_raw/failed_units.stdout)、[`crash_files.stdout`](../data/noPIE_prelink_validation/probe_raw/crash_files.stdout)、[`processes.stdout`](../data/noPIE_prelink_validation/probe_raw/processes.stdout)。这三项为 boot2 后续检查，boot1 的失败单元和 crash 文件清单没有同次采集。

对安全快速退出的 `/usr/bin/pulseaudio --version` 使用 `LD_DEBUG=libs`，VD glibc 输出两条 `prelink checking: ok`，远端返回码 0；原文在 [`diagnostic_pulseaudio.stdout`](../data/noPIE_prelink_validation/probe_raw/diagnostic_pulseaudio.stdout)。对 `tvs-daemon` 以加载器 `--list` 做不执行主程序的探查，远端返回码 0，但**没有**预链接诊断行（[`ld_list_tvs.stdout`](../data/noPIE_prelink_validation/probe_raw/ld_list_tvs.stdout)）；因此这次 `--list` 不能替代逐程序启动诊断。其余目标没有安全的 `--version` 退出契约，未为获得日志而启动服务第二实例。结论限于 `pulseaudio` 的运行时诊断与其余目标的静态标记，不能声称每个目标的整程序校验都已在运行时确认。

## 内存：GCC、LLVM 第三轮和本轮并列

这张表统一用**逐映射 smaps 相加**；新镜像来自 `collect.py` 保存的同次 smaps，历史四次来自原始 `02_steady/smaps_raw.txt.gz` 重新流式计算。它与 [`weekly_data_table.md`](weekly_data_table.md) 的用户进程/15 程序组 **smaps_rollup** 数值不同，不能混用；例如 GCC1 的用户态合计逐映射为 572,599 KiB，周报 rollup 为 579,416 KiB。历史逐映射来源及算法见 [`historical_smaps_same_source.tsv`](../data/noPIE_prelink_validation/historical_smaps_same_source.tsv)、[`historical_same_source.py`](../data/noPIE_prelink_validation/historical_same_source.py)。410 库名单及 15 条路径均固定为第三轮 [`classification.json`](../data/llvm_round3/analysis/classification.json)。表中“库”是文件映射 `Private_Dirty`，其他进程总量、栈和匿名为 Pss+SwapPss；PageTables 来自同次 meminfo。所有值为 KiB。

| 指标 | GCC 11-02 boot1/2 | LLVM3 11-03 boot1/2 | noPIE 11-13 boot1/2 | 三侧极差 GCC/LLVM3/noPIE | noPIE−GCC 均值 | noPIE−LLVM3 均值 |
|---|---:|---:|---:|---:|---:|---:|
| 用户进程 Pss+SwapPss | 572,599 / 554,891 | 557,390 / 548,902 | 540,855 / 539,875 | 17,708 / 8,488 / 980 | −23,380 | −12,781 |
| 15 程序组 Pss+SwapPss | 74,668 / 74,496 | 85,594 / 85,688 | 69,422 / 69,358 | 172 / 94 / 64 | −5,192 | −16,251 |
| 410 库：15 组 r-- 私脏 | 4,460 / 4,460 | 13,448 / 13,448 | 4,908 / 4,908 | 0 / 0 / 0 | +448 | −8,540 |
| 410 库：15 组 rw- 私脏 | 1,816 / 1,384 | 2,052 / 2,076 | 520 / 308 | 432 / 24 / 212 | −1,186 | −1,650 |
| 410 库：其余 r-- 私脏 | 56,420 / 56,044 | 62,304 / 61,996 | 59,740 / 58,984 | 376 / 308 / 756 | +3,130 | −2,788 |
| 410 库：其余 rw- 私脏 | 10,976 / 9,960 | 9,888 / 8,824 | 8,068 / 8,124 | 1,016 / 1,064 / 56 | −2,372 | −1,260 |
| 线程栈 Pss+SwapPss | 35,458 / 33,766 | 25,316 / 26,812 | 29,742 / 29,030 | 1,692 / 1,496 / 712 | −5,226 | +3,322 |
| 匿名映射 Pss+SwapPss | 195,610 / 184,133 | 171,575 / 171,848 | 175,607 / 174,590 | 11,477 / 273 / 1,017 | −14,773 | +3,387 |
| PageTables | 17,796 / 17,380 | 16,164 / 16,052 | 17,020 / 16,940 | 416 / 112 / 80 | −608 | +872 |

`r-- + rw-` 的 410 库私脏：15 程序组为 GCC 6,276/5,844、LLVM3 15,500/15,524、noPIE 5,428/5,216；其余进程为 GCC 67,396/66,004、LLVM3 72,192/70,820、noPIE 67,808/67,108。noPIE−GCC 的“其余进程”均值为 **+758 KiB**，小于 GCC 1,392 KiB 和 noPIE 700 KiB 的开机极差中的较大者，按本轮规则为**无显著差异**。其余上表绝对差值超过各自两侧极差的条目也只说明观测到跨镜像差，不说明原因。15 程序组包含未运行的 `acm-service`，其缺席会降低该组总量。

## 11-11 预算对比、专属库代码页和 13 个对象

用相同 `budget.py` 重算 11-11 LLVM，再以 `compare.py` 对新镜像两次预算：逐类 Pss 在 [`category_comparison.tsv`](../data/noPIE_prelink_validation/comparison/category_comparison.tsv)，四组前 50 文件在 [`comparison/`](../data/noPIE_prelink_validation/comparison/) 的 `top50_rx_loader_related_Pss_kB.tsv`、`top50_rx_text_Pss_kB.tsv`、`top50_r--_private_dirty_kB.tsv`、`top50_rw-_private_dirty_kB.tsv`。严格配对进程键 64，基线单侧 38、新镜像单侧 39；11-11 只采一次，所以 `compare.py` 正确标记“无波动数据，差值仅供参考”。类别示例：加载器相关 r-x Pss 63,790.9 → 新镜像均值 46,621.7（−17,169.2 KiB）；`.text` Pss 112,626.2 → 99,379.2（−13,247.0 KiB）。两项都可能包含服务集合与 LTO/MLGO 差异，**不作为预链接收益**。证据：[`comparison.md`](../data/noPIE_prelink_validation/comparison/comparison.md)、[`llvm1111_budget/derived_summary.json`](../data/noPIE_prelink_validation/llvm1111_budget/derived_summary.json)。

按 [`prelink_group_attribution.md`](prelink_group_attribution.md) 的乙组固定 62 个可信共同文件（GCC 已预链接、且 GCC 两次和 11-11 LLVM 的映射进程都只属于那 10 个带 `GNU_LIBLIST` 的程序），本轮两次这些库的 r-x Pss 为 **6,132/6,172 KiB**，极差 40；GCC 两次为 **7,212/7,132 KiB**，均值 7,172、极差 80；11-11 LLVM 单次为 **12,570 KiB**。本轮乙组相对 GCC 为 −1,020 KiB，相对 11-11 LLVM 为 −6,418 KiB。62 个文件在本轮两次均有映射，且没有新增的组外映射进程；路径、历史值在 [`per_file.tsv`](../data/prelink_group_attribution/per_file.tsv)，新镜像来自两份 `file_budget.tsv` 和 `vmas.tsv`，汇总见 [`first_part_summary.json`](../data/noPIE_prelink_validation/first_part_summary.json)。11-11 仅一次，无自身波动数据；这不是同镜像预链接开/关实验。

沿用 [`code_page_sections/analyze.py`](../data/code_page_sections/analyze.py) 的“文件偏移页与 ELF 节按字节重叠分摊”规则，tvs-daemon 与 tv-viewer 的 13 个对象在本轮两次 r-x 加载器相关节驻留均为 **596.417 KiB**，极差 0；11-11 LLVM 单次为 **5,041.677 KiB**；GCC 出厂态单次为 **576.651 KiB**。新镜像减 11-11 为 −4,445.260 KiB，减 GCC 为 +19.766 KiB。逐对象四列在 [`loader13_comparison.tsv`](../data/noPIE_prelink_validation/loader13_comparison.tsv)，本轮逐页结果在 [`pagemap13_loader_residency.tsv`](../data/noPIE_prelink_validation/pagemap13_loader_residency.tsv)，历史原表为 [`code_page_sections/object_summary.tsv`](../data/code_page_sections/object_summary.tsv) 与 [`factory1_pagemap13_loader_residency.tsv`](../data/prelink_undo_ab/attempt2/factory1_pagemap13_loader_residency.tsv)。旧两侧只有单次 pagemap，无法用开机极差判断此项是否显著；静态节大小也变化，故不能把 4,445 KiB 全归于预链接。

## LTO/MLGO 与解释边界

13 个对象按相同路径配对，新镜像相对 11-11 LLVM 的静态 `.text` 合计为 8,985,650 对 9,308,746 字节（−323,096）；`.dynsym` 为 681,760 对 899,328（−217,568）；`.rel.dyn` 为 530,208 对 434,040（+96,168）。逐对象见 [`static_13_vs_llvm1111.tsv`](../data/noPIE_prelink_validation/static_13_vs_llvm1111.tsv)。这些差可能来自 LTO、MLGO、PIE 与预链接的任意组合，现有镜像对比不能拆开因果；尤其 `.text` 和导出符号数不能归因预链接。本轮的静态预链接恢复得到确认，且 `pulseaudio` 的运行时检查为 `ok`；**预链接本身节省的内存尚未由同镜像控制变量实验直接测出**。

## 挂账与板子状态

- 11-11 的失败单元与 crash 目录基线、boot1 的同项健康输出未保存；不能判定“新增失败单元/新增 coredump”或两次健康波动。`acm-service` 两次缺席，需按服务启动日志另查原因，本轮未修复。
- 其余运行中目标没有安全快速退出的版本命令；加载器 `--list` 不打印预链接诊断，所以逐目标运行时 `ok/not prelinked` 未确定。可在受控实验镜像中配置启动日志验证，不能从静态标记推断全部运行时检查通过。
- 第二部分的“只撤销库预链接”尚未执行，因而不存在同镜像的预链接收益结论。第一部分提交并推送后先向用户回报，再决定是否进行第二部分。
- 板上本轮仅只读检查与两次冷启动；没有推送可执行文件或改写系统文件。最后一次 root off 后 UID=5001；证据 [`probe_result.json`](../data/noPIE_prelink_validation/probe_result.json) 的 `root_restored` 和 `boot_id_unchanged`。
