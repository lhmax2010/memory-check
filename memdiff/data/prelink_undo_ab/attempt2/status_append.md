
### GCC PERF 同镜像预链接撤销 A/B：出厂基线完成，撤销态安全停止（2026-11-12）

计划与门禁：沿用用户确认的 IP `192.168.108.26`，核对 armv7l、NT72671D、KSU2E、GCC 内核和 `BUILD_ID=T-KSU2EJAKUC-0101-PERF-202610010416`；`tvs-daemon` 的 `GNU_LIBLIST + .gnu.prelink_undo` 通过。8 个 prelink.conf 目录逐 ELF 扫描并拉回 438 个候选或目标，准备 17 个程序和 417 个库；434 个原件 SHA256/属性、主机 `prelink -u` 和空间门禁均通过。固定排除重签名的 boot-helper 与动态加载器；另排除无预链接程序标记的 TIFSDaemon 和字节串假阳性的 libdw。证据 `memdiff/data/prelink_undo_ab/attempt2/pull_classify.tsv`、`metadata.jsonl`、`undo_attempt2.tsv`、`stage_space_gate.json`。

进度：出厂态两次冷启动，身份、健康检查和 `prelink checking: ok` 均通过，稳态 smaps 完整。用户进程 Pss+SwapPss 为 576364/577422 KiB（极差 1058 KiB），15 个 GCC 非 PIE 程序组为 75471/75292 KiB（极差 179 KiB）。第一次 13 对象加载器相关节 r-x 驻留 576.7 KiB。第二次 `05_elf` 附件因 gzip 崩溃截断，已单列质量问题。证据 `factory_baseline_metrics.tsv`、`factory_baseline_noise.tsv`、`factory_attachment_validation.json`、`factory1_pagemap13_loader_residency.tsv` 和两次 `boot_result.json`。

停止条件：三次逐步尝试都在撤销态开机前安全停止；最后一次临时写入 13 个程序、0 个库后，`launchpad-loader` 退出即被自动重启，60 秒内无法取得无映射的原地覆盖窗口。所有临时改写已恢复，未形成完整的“仅撤销程序”或“全部撤销”状态，因此六类跨状态差值、波动和 LLVM 对照均未测得，不得当作预链接收益。报告 `memdiff/reports/prelink_undo_ab.md`；原始停机与恢复记录在 `memdiff/data/prelink_undo_ab/attempt2/`。

恢复核对：最终 14 个接触路径的原字节、权限和 xattr 核对 0 错误；冷启动后十个要求的进程均在、无新增失败单元和签名拒绝，诊断为 `prelink checking: ok`；AMD 激活单元 active，临时目录清理，root off 后 UID=5001。overlay upper 残留与原版字节一致的 copy-up 文件，可由重刷清除。证据 `recovery/original_verify.json`、`recovery/recovery_result.json`、`recovery/recovery_postboot_sdk_uid.stdout`、`recovery/overlay_after_recovery_reboot.stdout`。

挂账：需要可验证的受控办法阻止 `/init.scope` 中 launchpad-loader / launchpad-process-pool 自动重启并留出原地覆盖窗口，才能重新设计完整 A/B；本轮不再写系统 ELF。还需核对 ELF 打包时 gzip 崩溃及第一次 acm-service smaps 缺失。本次报告保留上一轮准备阶段的停止原文。
