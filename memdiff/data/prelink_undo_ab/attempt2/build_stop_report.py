#!/usr/bin/env python3
"""Publish the completed factory baseline and the safely stopped A/B attempt."""
from pathlib import Path
import datetime

HERE = Path(__file__).resolve().parent
MEMDIFF = HERE.parents[2]
REPORT = MEMDIFF / 'reports/prelink_undo_ab.md'

def main():
    previous = REPORT.read_text()
    if previous.startswith('# GCC PERF 同镜像预链接撤销 A/B：本轮结果'):
        previous = previous.split('## 上一次准备阶段的停止记录（原文）\n\n', 1)[1]
    new = '''# GCC PERF 同镜像预链接撤销 A/B：本轮结果

采集日期：2026-11-12；板子 `192.168.108.26`，`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202610010416`。**只完成出厂态的两次有效内存快照；撤销程序态、全部撤销态均未开机测量，因此本轮不能测出预链接收益。**证据位于 [`attempt2/`](../data/prelink_undo_ab/attempt2/)；上一次准备阶段的停止记录完整保留在文末。

## 准备与门禁

四项身份与 BUILD_ID 通过；`tvs-daemon` 的 `GNU_LIBLIST + .gnu.prelink_undo` 门禁通过，板上/主机 SHA256 相同。8 个目录中扫描 3,208 个 ELF，拉回并逐个用交叉 readelf 核对 438 个候选或目标。确认可准备撤销的有 **17 个程序、417 个库**；434 个原件的 SHA256、属主、权限及全部可枚举 xattr 已记录，434 个主机副本 `prelink -u`、标记消失与 ELF 类型校验均通过；板上空间 2,960,296 KiB，大于所需两倍容量 259,634 KiB。和 11 月 2 日 GCC 副本可配对的 426 个文件全部逐字节一致。依据：[`pull_classify.tsv`](../data/prelink_undo_ab/attempt2/pull_classify.tsv)、[`stage_space_gate.json`](../data/prelink_undo_ab/attempt2/stage_space_gate.json)、[`undo_attempt2.tsv`](../data/prelink_undo_ab/attempt2/undo_attempt2.tsv)、[`metadata.jsonl`](../data/prelink_undo_ab/attempt2/metadata.jsonl)。

固定排除：`boot-helper-dyboost-tv`（出镜像后重新签名）、`/usr/lib/ld-linux.so.3`（动态加载器）；逐 ELF 筛查又排除 `/usr/bin/TIFSDaemon`（无两项程序标记）、`/usr/lib/libdw-0.189.so`（字节串候选，readelf 无预链接标记）。本轮没有因属性不可恢复而排除的文件。依据：`pull_classify.tsv` 的 `selected`、`exclusion_reason` 列。

## 三个状态的执行结果

| 状态 | 冷启动 | 健康检查 | 预链接诊断 | 内存快照 |
|---|---:|---|---|---|
| 出厂 | 2/2 | 两次均十个要求的进程在运行、无新增失败单元或签名拒绝 | 两次均 `prelink checking: ok` | 两次 `02_steady` smaps 有效 |
| 仅撤销程序 | 0/2 | 未测得 | 未测得 | 未测得 |
| 全部撤销 | 0/2 | 未测得 | 未测得 | 未测得 |

出厂两次 boot ID 分别为 `af9b6596-73a7-423f-83fa-1eb106208876` 与 `c4140aa4-59b6-4346-b5d2-5d49f7bd174b`。健康检查里的六个失败单元两次完全相同，属于出厂基线。第一次 ELF 附件有效；第二次 `05_elf/elf_files.tar.gz` 在 gzip 进程崩溃后截断（tar 返回 2），但其 `02_steady/smaps_raw.txt.gz` 经 gzip 完整性校验通过。依据：[`factory_attachment_validation.json`](../data/prelink_undo_ab/attempt2/factory_attachment_validation.json)、两次 `boot_result.json`、`prelink_diagnostic.json`、`run.log` 与第二次 `post_dmesg`。这项附件缺陷不改变已采稳态 smaps 的完整性判定。

未进入撤销态的原因：第一次写入时 `tvs-daemon` 返回 `Text file busy`，阻塞式停 unit 超时；第二次改成非阻塞停 unit 后，运行中的 `tv-viewer` 无独立 systemd unit，写入仍返回 `Text file busy`；第三次对 `/init.scope` 的目标尝试按精确可执行路径 SIGTERM，`tv-viewer` 可退出，但 `launchpad-loader` 立即自动重启，60 秒内无法取得无映射的写入窗口。第三次**仅临时撤销写入 13 个程序、0 个库**，未完成 17 个程序集合；随后全部按原字节、权限和 xattr 恢复，且未在部分撤销状态下开机。先前两次尝试也均恢复并各自通过恢复开机检查。依据：[`apply_programs_retry_console.log`](../data/prelink_undo_ab/attempt2/apply_programs_retry_console.log)、[`touched_paths.jsonl`](../data/prelink_undo_ab/attempt2/touched_paths.jsonl)、[`recovery/original_verify.json`](../data/prelink_undo_ab/attempt2/recovery/original_verify.json)、[`recovery/recovery_result.json`](../data/prelink_undo_ab/attempt2/recovery/recovery_result.json)。

## 出厂态观测与未测项目

以下为 KiB，口径及逐次来源见 [`factory_baseline_metrics.tsv`](../data/prelink_undo_ab/attempt2/factory_baseline_metrics.tsv) 和 [`factory_baseline_noise.tsv`](../data/prelink_undo_ab/attempt2/factory_baseline_noise.tsv)。进程合计取 `proc_rollup.txt` 的 Pss+SwapPss；库映射取 `smaps_raw.txt.gz` 的 Private_Dirty 或 r-x Pss。15 组按先前分类表的 GCC 非 PIE 主程序路径；仅十程序使用的库按两次出厂开机的映射进程集合分类。第一次 `acm-service` 在同次 `ps.txt`/`proc_rollup.txt` 存在而 smaps 缺失，15 组进程总量纳入该进程，库映射私脏则无法补齐。这限制两次库指标的质量。

| 指标 | 出厂 1 | 出厂 2 | 开机间极差 |
|---|---:|---:|---:|
| 全部用户进程 Pss+SwapPss | 576,364 | 577,422 | 1,058 |
| 15 个 GCC 非 PIE 程序组 Pss+SwapPss | 75,471 | 75,292 | 179 |
| 417 个库 r-- 私有脏页，15 组 / 其余 | 4,132 / 56,588 | 4,352 / 56,628 | 220 / 40 |
| 417 个库 rw- 私有脏页，15 组 / 其余 | 312 / 9,416 | 1,804 / 10,016 | 1,492 / 600 |
| 417 个库 r-x Pss，仅十程序使用 / 也由其他程序使用 | 7,076 / 33,255 | 7,680 / 33,248 | 604 / 7 |
| PageTables | 17,768 | 17,884 | 116 |
| MemAvailable | 1,110,776 | 1,108,080 | 2,696 |

第一次出厂开机的 13 个对象 pagemap 采集成功，加载器相关 ELF 节 r-x 驻留合计 **576.7 KiB**；撤销态没有对应测量，故三态差值及波动均**未测得**。依据：[`factory1_pagemap13_loader_residency.tsv`](../data/prelink_undo_ab/attempt2/factory1_pagemap13_loader_residency.tsv)、[`pagemap13/`](../data/prelink_undo_ab/attempt2/boots/factory_1/pagemap13/)。

请求的“撤销程序−出厂”与“全部撤销−出厂”的六类差值、噪声比较，以及与 LLVM 第三轮 +13.9 MiB 私有脏页、+14.8 MiB 15 程序组、+5.4 MiB 专属库 r-x 的吻合程度：**全部未测得，不能判断**。出厂态两次开机极差仅供后续同法实验参考，不是预链接收益。

## 恢复与挂账

最后一次恢复逐个核对 14 个曾接触路径（含尝试但未改写的 `launchpad-loader`），SHA256、属主权限和 xattr 均无错误；冷启动后身份/BUILD_ID 通过，十个进程在运行，无新增失败单元或签名拒绝，诊断恢复 `prelink checking: ok`。AMD 的 `ac.socket`、`amd-tizen-action-service.socket`、`ac.service` 均恢复 active/running。暂存目录 `/opt/usr/prelink_ab_stage` 与工具目录 `/root/prelink_ab_tools` 均已清理；`sdb root off` 后 UID=5001。依据：[`recovery/original_verify.json`](../data/prelink_undo_ab/attempt2/recovery/original_verify.json)、[`recovery/recovery_result.json`](../data/prelink_undo_ab/attempt2/recovery/recovery_result.json)、`recovery_postboot_sdk_uid.stdout` 与 `recovery_amd_activation_units.stdout`。最终 boot ID `46721947-1f98-45c1-a5b5-9cdfa9abc4a6`。

overlay 上层仍有本轮 copy-up 的程序副本，字节与原版一致；[`overlay_before_recovery_reboot.stdout`](../data/prelink_undo_ab/attempt2/recovery/overlay_before_recovery_reboot.stdout) 和 [`overlay_after_recovery_reboot.stdout`](../data/prelink_undo_ab/attempt2/recovery/overlay_after_recovery_reboot.stdout) 保留恢复前后清单。重刷镜像可清除此类上层副本。**挂账**：要完成 A/B，需有可验证且受控的办法阻止 `/init.scope` 中 `launchpad-loader` / `launchpad-process-pool` 的自动重启并留出原地覆盖窗口；本轮不再尝试系统 ELF 写入。下一次还应核对 `05_elf` 打包异常与第一次 `acm-service` smaps 缺失。

## 上一次准备阶段的停止记录（原文）

'''
    REPORT.write_text(new + previous)
    print('已结束', datetime.datetime.now().isoformat(), '状态=成功', flush=True)

if __name__ == '__main__':
    main()
