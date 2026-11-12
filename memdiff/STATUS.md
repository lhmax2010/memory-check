# LLVM 预链接失效镜像内存分析状态

日期：2026-11-02 至 2026-11-03（Asia/Shanghai）。状态：执行、分析、板上恢复清理均已完成；最终报告见 reports/llvm_prelinkbroken_report.md。

## 计划与进度

1. 静态准备：完成，见 reports/tpms_memory_method.md。
2. 当前开机只读普查：完成并已本地提交，见 reports/survey.md。
3. 两次 memcheck 开机和一次 TPMS 开机：boot1、boot2 已采集并拉回；boot3 默认全套及失败用例补测已归档/存库；cmdline 补测 2 次已用尽。
4. 分析报告已完成；恢复设置、卸载测试依赖、清理板上目录并恢复 sdb root off 已完成。

## 已闭合事实与证据

- 用户已将材料目录更正为 `/home/linhao/Downloads`；七份材料齐全，已移动到 `memdiff/inputs/`，源目录不再留存这些文件。大小与 SHA-256 见 `memdiff/data/preflight/input_move.json`。
- TPMS 源码目录为 `/home/linhao/lss/memory_check/TPMS`；提供的源码无 Git 元数据，已就地初始化本地 `memdiff` 分支，无远程配置。本轮仅本地提交，作者 Hao Lin <hao.lin@samsung.com>。
- 初始阻塞已解除，旧状态保留在 `memdiff/data/preflight/STATUS_initial_blocked.md`。本轮需求快照为 `memdiff/inputs/requirement.txt`。

## 执行记录

初始准备阶段（历史记录）：当时尚未连接板子，未重启或修改设置。当前状态以本文件后续任务记录和 data/llvm_prelinkbroken/reboots.jsonl 为准。
本机命令均以 `nice -n 19 ionice -c3` 串行执行。

## 需要用户拍板的事项与挂账

当前无需用户决策。精确 GCC 历史跑法和数据库未提供，已按默认全套假设；用户已补充授权 TPMS 正常写入及依赖部署，见后文。
`/opt/usr/memcheck.sh` 与允许写入目录冲突，计划改用 `/opt/usr/memcheck/memcheck.sh` 并核查脚本路径依赖。
先前结论的可复算部分已核查，见任务 1 记录；因果判断仍留给用户与 Claude。

## 任务 1 完成

静态方法报告：`memdiff/reports/tpms_memory_method.md`；可复算脚本与结果：`memdiff/scripts/recompute_inputs.py`、`memdiff/data/static/recomputed.json`。
复核闭合：02_steady 总 Pss+SwapPss 差 +6324 kB（+1.1320%），纯 Pss 差 +12100 kB；TPMS IdleMemoryUsage 差 +7 MB、ProcessPSS 差 +44001 KB（来源在上述报告和 JSON 中）。不能把两套指标称为同口径。
14/83 的说法可按 comm 名称分组复现；完整 exe 路径分组结果不同，保留两套 TSV 供复核。预链接输入样本 GCC 58/102、LLVM 0/97，尚未复核当前板子。
未找到历史数据库和对应运行日志，按默认 TV 全套假设；精确历史顺序不能证明。默认全套违反本轮写入/部署限制，已异步询问用户选择适配或放宽这些限制；不影响先做身份核对及普查。

## 用户补充授权与普查进度

用户明确允许第 3 次开机 TPMS 正常流程所需的目录写入和依赖部署，要求测后恢复、清理。原限制对前两次 memcheck 仍适用。
初次板子身份四项通过，原始证据 `memdiff/data/llvm_prelinkbroken/survey/identity.txt`、`identity_checks.json`。初始 sdb shell 为 uid=5001；第一次创建目录被拒，后执行 `sdb root on` 得到 uid=0。结束时恢复 root off。失败及重试输出保留于 survey/operation_* 和 root_operation_*。
已采集状况快照和映射清单，当前正在串行拉取 ELF。prelinksh、vdprelink 的 RPM 查询显示未安装；不能仅凭包缺失推断预链接状态。

## 任务 2 完成

普查报告 `memdiff/reports/survey.md`；原始证据 `memdiff/data/llvm_prelinkbroken/survey/`，ELF 证据 `memdiff/data/llvm_prelinkbroken/elf/`。成功取得 1374 个文件，其中 95 个不同 exe 均为 PIE；1279 个映射库无预链接标记。超过 64 MiB 的 chromium 库未拉，deleted/不可达路径另列，不能外推到未取得对象。
当前板上无 memps，前两次不安装，单独记录 vd_memps 补充数据；第三次 TPMS 可按用户授权处理依赖。最小采集适配及理由见 survey.md 与 scripts/memcheck_runtime.patch，输入原件保持不变。
板上本轮已创建 `/opt/usr/memdiff/`，测后需要删除。sdb root 从 off 改为 on，结束时恢复 off。接下来按统一流程重启，进入正式 boot1。

2026-11-02T20:40:52.837855+08:00 boot1 已重启，身份通过；cmdline有效性=True。证据 data/llvm_prelinkbroken/boot1/latest_boot.json

## 正式 boot1 与后续准备

正式 boot1 已启动 memcheck，身份及 uptime 通过；完整记录在 data/llvm_prelinkbroken/boot1/，5 分钟轮询由 scripts/board_run.py 串行进行。板子墙钟与本机相差较大，保留原始时间，用 boot_id、uptime 和 Asia/Shanghai 本机事件日志核对顺序。
已准备 TPMS 默认用例运行适配入口 scripts/run_tpms.py，统一连接/重启身份核对、bash -c 形式、独立输出目录、设置原值采集及内存口径配对；不改 TPMS 源文件。用户授权已记入方法报告。尚未在板上执行 TPMS。
已通过 Python 语法解析和采集 shell 的 bash -n 检查；最终数据分析代码待实测样本验证，不能据未运行代码宣称结果。

boot1 的 15 分钟轮询已确认 steady=yes，02_steady 完成；窗口 CPU=19%，总 Pss+SwapPss=571691 kB，证据 data/llvm_prelinkbroken/boot1/memcheck_attempt_1/progress_03.stdout。此时仍在等待重复快照，尚不能标记整轮完成。
历史 14/83 分组已精确复算为 +14136/-878 kB，单边名称净差 -6934 kB，合计 +6324 kB；已注明 launchpad-proce 的 exe 碰撞与旧 LLVM ELF 归档 Broken pipe 限制，见 reports/tpms_memory_method.md、data/static/validation.json。

本机 TPMS 导入检查发现缺 PyUSB，已仅在 memdiff/runtime/python 安装 PyUSB 1.3.1（不改系统 Python）；安装来源/哈希报告与导入检查见 data/host_setup/。

boot1 的第 4/5 次轮询已确认 03_steady_repeat=572042 kB，04_after_drop_caches=572329 kB（总 Pss+SwapPss），第一轮尚在 ELF 打包，仍为 RUNNING。原始日志见 boot1/memcheck_attempt_1/progress_04.stdout、progress_05.stdout。快照名中的 steady 不替代 run_meta 的稳态标记。

2026-11-02T21:11:19.348042+08:00 boot1 memcheck 状态 DONE，结果 data/llvm_prelinkbroken/boot1/memcheck/llvm_boot1_20261102_044117；稳态标记见 00_info/run_meta.txt。

## boot1 完成及质量核查

状态 DONE、steady=yes、正式 cmdline 有效；未触发 FAILED 重测。三份 smaps 原始 gzip 全部校验通过；ELF tar.gz 截断，校验失败，禁止从该归档得出 ELF 结论。原始 tar_err 为短写，板上仍有约 2.8 GB 可用且 shell 文件大小限制为 unlimited；仅凭这些信息不能确定短写根因。证据 boot1/quality.json、boot1/memcheck/*/integrity.json、05_elf/tar_err.txt、boot1/post_memcheck_write_diagnostic.txt。普查阶段逐文件拉回的完整 ELF 独立保留。
`drop_caches` 实测为只写节点（--w-------），root 读取也 Permission denied，无法记录/恢复可读原值；这是执行清缓存的触发接口，未伪造原值或恢复成功。boot2 副本增加原值读取 stderr/权限记录，静止与采样逻辑不变。
原生 vd_memps 的 02_steady 配对有 102 个 PID，其 PSS 与 smaps Pss 合计差 +290 kB，而与 Pss+SwapPss 差 -125106 kB（SwapPss 合计 125396 kB）；后两次配对也接近 resident Pss。可支持 vd_memps 的 PSS 不含换出部分，不能直接替代尚未取得的 TPMS memps 实测结论。来源 data/analysis/measurement_summary.json 与对应 paired.tsv，记录的原始来源路径在 JSON 中。

2026-11-02T21:15:55.724833+08:00 boot2 cmdline 不一致，本次无效，证据 data/llvm_prelinkbroken/boot2/boot_validity_01.json

2026-11-02T21:16:58.342297+08:00 boot2 cmdline 不一致，本次无效，证据 data/llvm_prelinkbroken/boot2/boot_validity_02.json

2026-11-02T21:18:00.955418+08:00 boot2 cmdline 不一致，本次无效，证据 data/llvm_prelinkbroken/boot2/boot_validity_03.json

2026-11-02T21:18:00.955643+08:00 boot2 已重启，身份通过；cmdline有效性=False。证据 data/llvm_prelinkbroken/boot2/latest_boot.json

boot2 最终 cmdline 有效性=False，全局 cmdline 补测已使用 2 次；与 boot1 的差异为 ['- blperf=8_3_434', '+ blperf=8_3_435']。全部身份核对通过。按用户要求不再增加 cmdline 补测，继续采集并在报告中保留严格无效标记。证据 boot2/boot_validity_*.json、boot2/latest_boot.json。

已生成报告草稿 reports/llvm_prelinkbroken_report.md，明确“执行中”，包含 boot1 实测表和来源。TPMS 原始测量方法、默认 keepalive、时间常量均已核查并记录；内部重启将关联当前用例，避免只检查 boot3 最初一次开机。

boot2 已运行 30 分钟仍未满足 CPU 稳态阈值（最近完整窗口 25%，内存和 Swap 波动已达标），继续原定最多 45 分钟等待。证据 boot2/memcheck_attempt_1/progress_06.stdout。已补齐第三轮快照 CPU 前 20 的可复算脚本 snapshot_cpu_top.py，并用初始普查原始数据复核数值一致。

boot2 等待稳态 2705 秒后超时，最终窗口 CPU=24%、MemAvailable 波动 8948 kB、Swap 波动 548 kB，按未静止继续采样。02_steady 总量 562081 kB、Pss 436717 kB、SwapPss 125364 kB；与 boot1 总量相差 -9610 kB。这些数值来自 boot2/memcheck_attempt_1/progress_10.stdout，完整结果仍在采集。该轮 cmdline 无效且 steady=no，不得当作满足控制条件的有效重复。日志中的瞬时 PID 消失及 /proc/4kbtin 非目录报错保留，待拉回后核查数据完整性。

boot2 三次快照已完成，总 Pss+SwapPss 为 562081、562326、562354 kB，03 相对 02 增加 245 kB，04 相对 03 增加 28 kB。55 分钟检查时仍 RUNNING，正在 ELF 打包，未宣称附件完整。来源 boot2/memcheck_attempt_1/progress_11.stdout。全目录可执行文件扫描中的 EXEC 计数与“当前运行进程 exe 全为 PIE”的普查对象不同，不能混用。

2026-11-02T22:18:27.352861+08:00 boot2 memcheck 状态 DONE，结果 data/llvm_prelinkbroken/boot2/memcheck/llvm_boot2_20261102_051824；稳态标记见 00_info/run_meta.txt。

2026-11-02T22:19:08.608870+08:00 boot2 完整性核查完成：DONE、steady=no、cmdline 无效，三份 raw smaps gzip 均完整，ELF tar.gz 截断，未触发 FAILED 补测。证据 boot2/quality.json、memcheck/*/integrity.json；两轮分析已写入 data/analysis/ 和报告草稿。第三轮及恢复清理尚未执行。

boot2 ELF 截断补充证据：内核日志 uptime 3394.062179 记录 gzip(2714) 收到信号 6（SIGABRT），随后进入 coredump 流程，与打包时间相符；不能据此判断信号发送方或编译器根因。原始完整 dmesg 及节选在 boot2/post_memcheck_diagnostic/，其中 gzip_signal_excerpt.txt 为去 ANSI 的节选。未做反汇编、未修改保护设置、未重新压缩。

2026-11-02T22:21:29.839573+08:00 boot3 cmdline 不一致，本次无效，证据 data/llvm_prelinkbroken/boot3/boot_validity_01.json

2026-11-02T22:21:29.839866+08:00 boot3 已重启，身份通过；cmdline有效性=False。证据 data/llvm_prelinkbroken/boot3/latest_boot.json

第三轮身份核对通过，完整 cmdline 仍仅 blperf 不同，严格有效性=False，补测额度不增加。TPMS 部署前整套快照及原值已保存 boot3/tpms_before/、tpms/baseline/；默认全套已于 22:26 开始并进行其原定初始重启，运行入口 scripts/run_tpms.py。本机依赖仓库可达，未改变默认用例/等待/解析逻辑。新增部署前保护钩子保存可能被 RPM 覆盖的原文件：已发现 sys-tools 所属 /usr/bin/tinymembench，与板上及本机备份 SHA256 一致；证据 tpms/payload_preflight_ops/backup_validation.json。正常 RPM 安装流程保持原样，测后须恢复文件并核对 RPM 文件状态。

2026-11-02T22:27:19.387154+08:00 TPMS 内部重启 cmdline 不一致，证据 data/llvm_prelinkbroken/boot3/tpms/internal_reboots/1793629576726984819

2026-11-02T22:31:55.812705+08:00 STOP：身份核对或重启有效性失败，停止全部板上操作。证据 data/llvm_prelinkbroken/boot3/tpms/reconnections/1793629912794094099/identity/identity_checked.json

2026-11-02T22:31:55.990181+08:00 TPMS 执行中断：SystemExit('Identity check failed')；证据 data/llvm_prelinkbroken/boot3/tpms

2026-11-02T22:33:49.747953+08:00 上条身份失败的 fields 为空，stderr 为 target not found：属于传输未连通，未取得任何身份不符证据。保持测量停止，仅执行最长 15 分钟连接探测和四项身份核对；核对通过前不做测试或部署。

2026-11-02T22:37:56.808222+08:00 TPMS 首次执行在 booting_time_test 重连失败时中断（身份字段为空、target not found），已于 22:33:52 恢复且四项身份通过，没有身份不符证据。首轮工作目录、原始输出、日志保存在 boot3/tpms/attempts/attempt1/。传输层已区分读不到身份与实际不符：未连通最多重试 15 分钟，读到不符仍立即停止。现在从默认全套入口重跑，保留初始恢复基线及已部署依赖记录，不改测试/解析逻辑。

2026-11-02T22:39:45.806372+08:00 TPMS 内部重启 cmdline 不一致，证据 data/llvm_prelinkbroken/boot3/tpms/internal_reboots/1793630322613803983

2026-11-02T22:41:13.246013+08:00 TPMS 内部重启 cmdline 不一致，证据 data/llvm_prelinkbroken/boot3/tpms/internal_reboots/1793630409871454059

2026-11-02T22:46:29.727708+08:00 TPMS 内部重启 cmdline 不一致，证据 data/llvm_prelinkbroken/boot3/tpms/internal_reboots/1793630727028714754

TPMS 第二次完整入口执行正在进行，运行进程 stdout 为 boot3/tpms_driver.log，逐用例事件为 tpms/test_order.jsonl；已完成 build_info 和 booting_time，memps-0.2.0-0 已由原流程安装，memory_usage_test 于 22:45:27 发起其原定重启，按原代码等待 300 秒后再经身份重连采样。连接偶尔需重试，实际采样时刻必须从日志和 uptime 取值。

恢复准备的重要补充：本机隔离 RPM 数据库证明覆盖后卸载新包不会自动重置旧包 FILESTATES；仅恢复二进制不够。已在内核包部署前通过 rpmdb --exportdb 保存板上原始记录于 tpms/rpm_restore_support/original.headers（当时仅 systemd-analyze 是本轮新增），并提取 sys-tools.original.header、header_index.json。原始 tinymembench 的 FILESTATE=0、SHA、rpm -V sys-tools 及本机/板上备份见 tpms/payload_preflight_ops/ 和 payload_backup_files/。本机隔离验证“rpm -e --justdb --nodeps --noscripts --notriggers <包> + rpmdb --importdb < 原 header”能恢复原记录，见 data/host_setup/rpm_selective_header_restore_probe.json；尚未在板上执行该恢复，测后先在 /opt/usr/memdiff 下的隔离 db 验证，再只对确有标记变化的原包恢复，禁止整库覆盖。RPM 文件冲突保护脚本 preserve_payload.py 在正常 push RPM 前保存已有非目录文件，持续记录 payload_preservation.json、payload_preservation_ops/ 和板上 /opt/usr/memdiff/payload_backups/。

2026-11-02T22:52:43.196896+08:00 TPMS 内部重启 cmdline 不一致，证据 data/llvm_prelinkbroken/boot3/tpms/internal_reboots/1793631100546209342

TPMS 内存用例及配对完成：pair/smaps_raw.txt.gz 完整校验通过（pair/integrity.json）。共同 102 PID、前后 COMMAND 一致的 19.2 秒窗口中，memps PSS 与 smaps Pss 合计误差 -138/+297 kB，SwapPss 合计 132492 kB，前后 memps 漂移 435 kB；支持 memps PSS 不含 swap。证据 data/analysis/tpms_common_cohort.{json,tsv} 及 boot3/tpms/pair/。原始 TPMS memps.txt 给出 TOTAL PSS=422000 kB，Used (Mem+Swap)=480 MB（492360 kB）；report.txt 已由原解析器写出 IdleMemoryUsage=480，尚待完整全套结束后正常入库核验。当前已进入 app_launching_test，NAND 可选 XLSX 导出提示未安装 xlsxwriter，原指标解析返回码为 0，该附件缺失需单列，不等于已有指标无效。

2026-11-02T22:55:54.666200+08:00 TPMS 内部重启 cmdline 不一致，证据 data/llvm_prelinkbroken/boot3/tpms/internal_reboots/1793631292007624090

Dali 默认用例失败的执行方原因已查明：旧版 payload 保护器把每条 RPM 路径展开进 bash -c，较长清单触发 Argument list too long；证据 tpms/payload_preservation_ops/1793631622355310648/run.stderr 和 driver.log，对此不得判为镜像性能失败。FFmpeg 在问题确认时已于 23:03:40 开始，本轮默认全套继续保留。已把保护器改为固定长度 shell + TSV 数据文件（preserve_payload_v2.py），旧版留作 preserve_payload_v1.py。运行中的 Python 已载入旧版，通过仅本进程 PATH 可见的 runtime/bin/rpm 桥接器拦截其 host -qpl：先完整执行 v2 保护并保存真实清单，再告诉旧保护器没有剩余待处理路径；板上的 RPM 安装命令及测量/解析逻辑不变。新启动的入口直接使用 v2。后续大型 RPM 推送会使用修正流程。全套结束后须单独补测 Dali，保留默认全套失败记录与补测结果，使用独立补测 DB/工作目录；主全套 DB 不得被仅 Dali 的新 build 替代。NAND 可选 XLSX 附件也待本机补齐。

2026-11-02T23:14:54.536367+08:00 TPMS 内部重启 cmdline 不一致，证据 data/llvm_prelinkbroken/boot3/tpms/internal_reboots/1793632431870404718

2026-11-02T23:19:59.670706+08:00 TPMS 执行中断：CalledProcessError(1, ['/usr/bin/python3', '/home/linhao/lss/memory_check/TPMS/memdiff/scripts/snapshot_cpu_top.py', '/home/linhao/lss/memory_check/TPMS/memdiff/data/llvm_prelinkbroken/boot3/tpms_after'])；证据 data/llvm_prelinkbroken/boot3/tpms

已按原 XML 生成器和 save_result_to_db.sh 做核心测量检查点入库，保存在 boot3/tpms/checkpoints/core_measurements/，明确是部分进度而非完整全套 DB。实测发现原 TPMS DB 唯一索引 + INSERT OR IGNORE 仅保留重复启动阶段的第一条：XML main=169/89 ms、create=10/11 ms，DB=169/10，XML 均值=129/10.5。方法报告与对比脚本已区分两种口径；禁止改 TPMS 源代码“修正”数据库，也不可将历史汇总表当作已证实的同聚合基线。

默认全套第二次入口已执行所有默认函数，正常 XML 已按原 save_result_to_db.sh 入库，tpms/tpms.db 共 130 行；全套原始工作目录另存 tpms/raw_export/。原 runner 在结束快照拉取不完整时退出，归档补救见 full_suite_archive_status.json。失败用例为 Dali、FFmpeg、GStreamer、kernel、dotnet，保留失败数据，准备独立工作目录/数据库补测。
进一步核查实际 sdb shell 为 uid=5001，root on 后恢复 uid=0，随后能访问 memdiff 内文件；v2 保护器失败 stderr 为 Permission denied。证据 tpms/recovery_probe/permission*.stdout。补测传输层在每次身份核对通过后重新 root on 并确认 uid=0，校验推拉 SHA256；原指标采集与解析代码保持不变。失败的传输自检仅执行 echo/sleep，未重跑性能用例，全部日志保留 transport_validation*。

NAND 可选 XLSX 附件已仅在本机用原始 rpm_qai.txt 和原解析器补齐，未重复采样或再次写主 DB。验证及命令见 tpms/nand_xlsx_recovery/validation.json；依赖仅安装于 memdiff/runtime/python，来源 data/host_setup/xlsxwriter_install.json。

Dali 独立补测脚本退出 137、原解析器退出 255，原 TPMS 函数却返回 True，不能当作有效成绩。stdout 显示执行 pgrep -f enlightenment_info 后 kill -9 匹配进程；bash -c 的脚本文本本身含该字符串，从而把自身包含在匹配集合中。证据 supplemental/transport/1793634643168800978_job/、supplemental/runner.log；需区别于镜像自身性能问题。运行副本的三个字符串字面量改为相邻引号拼接，运行时名称/文件名逐字节相同，但命令行文本不再含连续匹配字串；变更及本机验证见 scripts/dali_bash_c_compat.patch、data/host_setup/dali_bash_tokenization_validation.json。原 TPMS 源文件、用例逻辑/次数/解析未改，待当前补测完后单独重跑 Dali 并另存失败前后证据。

当前独立补测控制器记录见 tpms/active_controller.json（主入口 scripts/run_tpms_supplement.py，当前会话执行 ID 58854）。FFmpeg 已完成 H.264 部分并进入 HEVC；观察到 HEVC 输出提取 FPS 失败，仍按原 5 次和 3600 秒上限继续。不能把有 DONE 状态的后台作业或原函数 True 等同为所有子指标有效。实时只读进度证据保存在 tpms/supplemental/progress/。
后续顺序：等待此五用例补测结束；用 TPMS_SUPPLEMENT_DIR=dali_retry、TPMS_SUPPLEMENT_CASES=dali_3d_ui_test 启动修正 UEP 字面量后的单独 Dali；再核对实际部署清单，恢复/卸载本轮新增项目，完成收尾重启和 root off。不要在当前控制器运行时另起整套测试或清理。主全套 DB 保留不替换。微基准 Bench 路径和 /tmp/perf-* 在 .NET 部署前均不存在，证据 supplemental/late_deployment_baseline/paths.stdout，可作为测试生成目录的清理依据。

时间解释修正：板上 date 明示 PST、stat 时间偏移 −0800，本机为上海 +0800；16 小时显示差由时区解释，并非已证实的时钟漂移。换算 UTC 的核验证据 data/analysis/timezone_validation.json。此前“墙钟不一致”仅表示原始显示不同，采集顺序仍以 boot_id/uptime 和带时区主机事件确定。

上述时区核验也保留了残差：同一次短查询换算 UTC 后，板上 date 比主机事件时间快约 23.08 秒。不能把时区解释写成“两端时钟完全同步”；单次观测也不能推断漂移率，跨端对齐继续使用 boot_id/uptime 与主机单调计时。

HEVC 补测已有板上运行失败证据：supplemental/ffmpeg_diagnostic/ 内完整 dmesg 多次记录 ffmpeg 收到 SIGABRT（6），信号汇总为 signal_summary.json。不能将 HEVC 无 FPS 全归为传输问题；发送方/根因未确定，未改保护设置，仍执行原循环。

FFmpeg 已结束并拉回：四配置均执行五次，但有效样本分别为 5/4/0/0（H264 1080p/H264 4K/HEVC 1080p/HEVC 4K），质量文件 supplemental/ffmpeg_result_quality.json，可用 scripts/check_ffmpeg_samples.py 复算。GStreamer 于 00:35:22 开始，现已进入 HEVC 4K；原脚本固定 1000 帧除耗时且不检查管线退出码，正数 FPS 不能独自证明完整解码，限制写入 reports/tpms_execution.md。补测控制器仍是 58854，不得同时清理。

2026-11-03T01:26:33.425041+08:00 TPMS 单独补测结束，原始结果与独立数据库见 data/llvm_prelinkbroken/boot3/tpms/supplemental；恢复清理待执行。

GStreamer 补测结束进入 kernel。原输出四配置均给出五条数字，但内核日志两次 gst-launch-1.0 SIGABRT 以 uptime/板上时间对齐到 HEVC 4K 第 4/5 次循环，证据 supplemental/gstreamer_result_quality.json，复算脚本 check_gstreamer_samples.py。正数 FPS 不能把这些异常循环判有效；其余配置无管线退出码，不声称逐次解码完整。具体限制已写入 reports/tpms_execution.md。

2026-11-03T08:22:25.166720+08:00 TPMS 单独补测结束，原始结果与独立数据库见 data/llvm_prelinkbroken/boot3/tpms/dali_retry；恢复清理待执行。

## 最终恢复与交付（2026-11-03）

19 个本轮新增 RPM 和 WGT 应用已移除；Dali 残留注册在规范重启后消失。原 /usr/bin/tinymembench 的 SHA256、权限、所有者、时间戳和 Smack 属性恢复，sys-tools RPM 文件状态查询与部署前导出的原始记录逐字节一致。六项 vconf、四个 governor、RPM/应用/cyad 清单在最终重启后全数匹配基线。测试专用 syslibs、Bench、临时路径和 /opt/usr/tpms、/opt/usr/memdiff、/opt/usr/memcheck 均已清除，sdb root off 后 uid=5001，四项身份仍通过。最终重启 boot_id 已变化、uptime<900 秒，但完整 cmdline 仍无效，不增加已用尽的两次补测额度。证据 data/llvm_prelinkbroken/cleanup/summary.json 及其引用文件。drop_caches 原缓存内容不可恢复，已单列。

Dali 兼容复测目标作业实际 8.7 秒 rc=0，但执行文件因 Dali::Application::New 未定义符号失败，FPS 文件为空；数据库 0 fps/hasTimedOut=1 是原解析器标记，不能误称 90 秒运行超时。Kernel 四个工具被拒绝执行，.NET 用例实际完成。FFmpeg 只有 H.264 1080p 满 5/5 有效，GStreamer HEVC 4K 两次 gst-launch 收到 SIGABRT；详见 reports/tpms_execution.md。

## 第二轮：干净 GCC 基线与新 LLVM 数据对比

2026-11-03 开始。按用户新规则仅排除 cmdline 的 blperf 参数；各镜像内部其余参数必须一致。PSS 对比统一来源，TPMS 内存指标并列同次采样 swap 已用量。沿用第一轮测量脚本、v2 payload 保护器及 robust transport；完成后按原始基线恢复并重启核验。全部新证据位于 data/gcc_baseline/，不改第一轮原始数据。

2026-11-03T09:58:58.721960+08:00 第二轮复核：LLVM boot1/boot2/boot3 按排除 blperf 的规则重新判定为 [('boot1', True), ('boot2', True), ('boot3', True)]；boot2 steady=no 和两轮 ELF 截断事实不变。证据 data/gcc_baseline/preflight/llvm_cmdline_revalidation.json。

2026-11-03T10:18:20.955187+08:00 第二轮 GCC 不重启普查与 ELF 逐文件统计完成，完整 dmesg/信号筛选见 data/gcc_baseline/survey/。

2026-11-03T10:20:42.969484+08:00 第二轮阶段控制器中断：CalledProcessError(1, ['/usr/bin/python3', '/home/linhao/lss/memory_check/TPMS/memdiff/scripts/round2_survey_finish.py'])

2026-11-03T10:22:08.736317+08:00 第二轮 GCC 普查完成：ELF 汇总 {"mapped_so_total": 1362, "mapped_so_unmarked": 947, "exec_DYN": 86, "exec_PIE_confirmed": 86, "exec_EXEC": 15, "exec_PIE_not_confirmed": 15, "mapped_so_prelinked": 415}；当前开机完整 dmesg 的 signal 6/11/4 记录数=0。编译器 GCC 14.2.0，内核构建日期 2026-09-30，cmdline 无 crashkernel；不可读/超限路径和 prelinksh 查找证据均已保留。

2026-11-03T10:23:17.940194+08:00 boot1 已重启，身份通过；cmdline有效性=True。证据 data/gcc_baseline/boot1/latest_boot.json

第二轮 boot1 首次五分钟轮询曾断连，约 467 秒后在 15 分钟内恢复；GCC 身份通过且 boot_id 未变，后台采集仍 RUNNING，没有为恢复连接额外重启。证据 data/gcc_baseline/boot1/transport_recovery_summary.json。

第二轮 boot1 等待 2705 秒仍未静止（窗口 CPU=25%，MemAvailable 波动 6544 kB、Swap 波动 0），按原脚本继续三次快照，不降低阈值、不额外重测。该轮需标注 steady=no；证据 data/gcc_baseline/boot1/memcheck_attempt_1/progress_1793675771234673407.txt。

2026-11-03T11:22:20.518431+08:00 第二轮 boot1 memcheck DONE，稳态、归档完整性见 data/gcc_baseline/boot1/quality.json；完整 dmesg 已保存。

第二轮 GCC boot1 已由采集器返回 DONE，但 run.log 记录 ELF 打包报错；完整 dmesg 明确记录 gzip 收到 SIGABRT（6），证据 data/gcc_baseline/boot1/post_memcheck_diagnostic/dmesg_full.stdout 及 signals.json。因此 gzip 异常不能视为 LLVM 独有；归档完整性待拉回校验，DONE 不触发 FAILED 重测规则。

2026-11-03T11:23:25.808798+08:00 boot2 已重启，身份通过；cmdline有效性=True。证据 data/gcc_baseline/boot2/latest_boot.json

2026-11-03T12:24:44.924266+08:00 第二轮 boot2 memcheck DONE，稳态、归档完整性见 data/gcc_baseline/boot2/quality.json；完整 dmesg 已保存。

2026-11-03T12:26:14.796933+08:00 boot3 已重启，身份通过；cmdline有效性=True。证据 data/gcc_baseline/boot3/latest_boot.json

2026-11-03T12:27:03.507363+08:00 第二轮两次 memcheck 均 DONE，cmdline（仅去 blperf）有效，均 steady=no；六份 smaps gzip 完整，但两份 ELF 归档均截断且各有 gzip SIGABRT 直接证据。四开机共 12 份 rollup 汇总已独立复算一致，见 data/gcc_baseline/analysis/four_boots_rollup_validation.json。统一 rollup 的 Pss+SwapPss 均值 GCC=570545、LLVM=566886 kB，LLVM−GCC=-3659 kB，小于两侧开机极差 17742/9610 kB；GCC 非 PIE 路径组增量 +10575 kB（极差168/736）；确认预链接标记丢失库的映射 Private_Dirty 增量 +14126 kB（极差1824/636）。来源分别为 analysis/userspace_four_boots.tsv、executable_groups_four_boots.tsv、library_groups_private_dirty_four_boots.tsv。两侧服务路径存在性不同，不能把系统净差解释为相同工作负载下的编译器效应；TPMS 与最终恢复尚未完成。

2026-11-03T13:13:13.718420+08:00 第二轮 TPMS 默认全套已运行到 ffmpeg_benchmark_test；前序 build_info、booting_time、memory_usage、app_launching、web_app_launching 等方法返回 True。Dali 方法亦返回 True，但 workspace/10.0-tv-kantsu2e/now_testing/enlightenment_info_com.samsung.dali-demo.txt 为 0 字节，runner.log 中原解析器写 test_state=fail 且报 fail to get fps data。默认结果保留；结束后按原失败用例规则在独立目录补测 Dali，不把方法 True 误判为有效 FPS。

2026-11-03T13:29:06.470350+08:00 第二轮 GCC TPMS 默认 FFmpeg 方法返回 True，但 workspace/10.0-tv-kantsu2e/now_testing/ffmpeg_benchmark_result.txt 原始四配置有效样本分别 H264 1080p=5/5、H264 4K=5/5、HEVC 1080p=3/5、HEVC 4K=0/5；boot3/tpms/case_dmesg/ffmpeg_benchmark_test/signals.json 捕获 ffmpeg signal 6 三次。方法 True 不代表全部配置有效。默认数据保留；完成后将它与 Dali 一起作为原始质量失败的独立补测对象（若默认失败方法自动补测中未包括）。

2026-11-03T13:57:11.928927+08:00 第二轮 GCC TPMS 默认 GStreamer 方法返回 True，workspace/10.0-tv-kantsu2e/now_testing/gstreamer_benchmark_result.txt 四配置各报告 5 个数值样本，但 case_dmesg/gstreamer_benchmark_test/signals.json 有 gst-launch-1.0 SIGABRT 三个事件。以同一持久作业 start_uptime 与原始 Start time 对齐，三个事件约落在 HEVC 4K 迭代 3、4、5 内；FFmpeg 的三次 SIGABRT 同样约落在 HEVC 4K 迭代 3、4、5 内。对齐用的脚本已准备，因本机低优先级磁盘读取受测试负载影响，待测量结束再生成并复核正式中间表；不能把 GStreamer 数值 FPS 当作三次解码成功。默认结果保留，质量补测与 Dali、FFmpeg 合并到独立目录。

2026-11-03T14:11:03.200809+08:00 第二轮 GCC TPMS 默认 kernel_benchmark_test 方法返回 True，runner.log 中 18 个 kernel 测量记录均由原解析器标为 success；随后进入 dotnet_benchmark_test。与第一轮 LLVM 补测的 kernel 工具执行拒绝形成可复核的执行差异，不能据此单独推断根因。

2026-11-03T14:17:23.775561+08:00 第二轮 TPMS 默认全套结束，原始结果和独立默认数据库见 data/gcc_baseline/boot3/tpms/；失败用例补测与恢复尚待完成。

2026-11-03T14:17:59.058612+08:00 第二轮阶段控制器保护性停在提交前：发现第一轮 LLVM transport 目录中新出现本轮 TPMS 调用日志 1153 条；完整路径、字节数与 SHA256 已转存 data/gcc_baseline/boot3/tpms/misrouted_transport/misrouted_records_manifest.json。旧跟踪证据未改。

2026-11-03T14:22:46.548797+08:00 第二轮默认 TPMS 数据已完整留存，DB 176 行且完整性通过；Dali 数据库超时，FFmpeg HEVC 4K 0/5 有效并有 SIGABRT，GStreamer HEVC 4K 有 SIGABRT。质量补测选 Dali、FFmpeg、GStreamer，独立目录和数据库。原沿用的第一轮 sdb 传输包装器将本轮 1153 条调用记录误写为 LLVM transport 新目录；已逐条核对为本轮调用并转存 GCC misrouted_transport，第一轮跟踪数据未改，后续调用采用同逻辑的 GCC 路径包装器。

2026-11-03T15:21:11.653775+08:00 TPMS 单独补测结束，原始结果与独立数据库见 data/gcc_baseline/boot3/tpms/quality_retry；恢复清理待执行。

2026-11-03T15:35:46.383928+08:00 第二轮板子最终恢复完成：Dali 包管理残留记录已在备份和逐表审核后定点注销；最终重启后 vconf、governor、RPM、应用、cyad、原文件属性与关键挂载点均匹配部署前基线，本轮目录已清理，sdb root off 后 uid=5001。证据 data/gcc_baseline/cleanup/summary.json。

2026-11-03T15:41:25.121279+08:00 第二轮独立 TPMS 质量补测完成，结果与默认全套分开保存：Dali 再次出现 0 字节原始帧率文件和数据库失败行；FFmpeg HEVC 4K 再次 0/5 有效样本，ffmpeg SIGABRT 3 次；GStreamer HEVC 4K 虽有 5 个数值样本，gst-launch-1.0 SIGABRT 3 次。四个默认/补测媒体用例的信号均对齐至 HEVC 4K 第 3–5 次迭代，见 data/gcc_baseline/analysis/tpms_case_quality.json、media_signal_alignment.tsv。补测不替换默认 DB。

2026-11-03T15:41:25.121355+08:00 第二轮最终报告已落盘 reports/final_gcc_vs_llvm.md；统一 rollup 的 Pss+SwapPss 均值 LLVM−GCC=-3659 kB，低于两边极差；GCC 非 PIE 路径组 +10575 kB、GCC 已预链接而 LLVM 未标记库的映射私有脏页 +14126 kB，均超两侧极差，但关联并不证明唯一因果。GCC boot1/boot2 身份及 cmdline 有效、DONE，均 steady=no 且 ELF 归档截断，故仅为条件受限重复样本。TPMS 内存指标同采样 swap 已并列，第一轮同 LLVM 镜像的约 51 MB/75 MB 运行间波动已列为结论限制。板子最终恢复审计通过，见 data/gcc_baseline/analysis/final_audit.json 与 cleanup/summary.json。

## 第三轮：新 LLVM 镜像 VD 板收益来源拆解

2026-11-03T17:22:35.016904+08:00 已核对 memdiff 分支及前两轮 STATUS；先执行四项板子身份检查，不合格立即停止。第三轮数据写 data/llvm_round3/，不更改构建配置或 TPMS 用例。

2026-11-03T17:37:46.446295+08:00 第三轮执行中断：CalledProcessError(1, ['/usr/bin/python3', '/home/linhao/lss/memory_check/TPMS/memdiff/scripts/round3_analyze_elf.py'])；必须按身份/连接/运行证据判断下一步，禁止覆盖原始证据。

2026-11-03T17:46:59.636301+08:00 第三轮 LLVM 普查完成：ELF 汇总 {"mapped_so_total": 1302, "mapped_so_unmarked": 1302, "exec_DYN": 101, "exec_PIE_confirmed": 101}；当前开机完整 dmesg 的 signal 6/11/4 记录数=4。内核构建日期 SMP PREEMPT Mon Nov  2 16:16:32 UTC 2026，cmdline 不含 crashkernel=；不可读/超限路径和 prelinksh 查找证据均已保留。

2026-11-03T17:48:47.648215+08:00 第三轮不重启普查与 ELF 统计完成；普查收尾期间曾短暂断连，已在 15 分钟限额内恢复并重新核对 LLVM 身份，没有额外重启。新镜像内核构建日期 SMP PREEMPT Mon Nov  2 16:16:32 UTC 2026，第一轮为 SMP PREEMPT Fri Oct 30 16:39:29 UTC 2026；rpm -qa 规范包清单与第一轮 TPMS 部署前清单同为 2342 项，按包名/版本无差异。运行中 PIE 路径从 95 到 101，非 PIE 均 0；已加载库的预链接标记仍为 0。证据 data/llvm_round3/analysis/round1_vs_round3_image.json、round1_vs_round3_packages.tsv；统计受两次普查进程集合差异限制。

2026-11-03T17:50:58.322760+08:00 boot1 已重启，身份通过；cmdline有效性=True。证据 data/llvm_round3/boot1/latest_boot.json

2026-11-03T18:52:13.547680+08:00 第三轮 boot1 memcheck DONE，稳态、归档完整性见 data/llvm_round3/boot1/quality.json；完整 dmesg 已保存。

2026-11-03T19:00:01.225892+08:00 第三轮 boot1：原流程 STATUS=DONE、cmdline 有效，steady=no；末窗口仅内存稳定（MemAvailable/Swap 波动 6592/292 kB，小于 16007 kB），CPU=21%。三份 smaps gzip 完整；ELF tar 校验失败且 dmesg/crash 目录存在 gzip 崩溃证据。依用户补充指示，boot2 保持原 45 分钟静止判定并执行完整第 6 步，不复用此无效归档。boot1 同次开机服务核查已完成：perception-engine manifest on-boot=false；acm-service 实际 systemd 单元 inactive、其 path active waiting；storaged active running；bnr-service manifest on-boot=false 且本次在运行。journal 无持久日志，dlog 各 ring 未提供相关记录；仅见 gzip crash 报告。首次服务采集参数误位的 rc=127 与修正后证据均保存。

2026-11-03T19:02:31.559124+08:00 boot2 已重启，身份通过；cmdline有效性=True。证据 data/llvm_round3/boot2/latest_boot.json

2026-11-03T20:03:57.473649+08:00 第三轮 boot2 memcheck DONE，稳态、归档完整性见 data/llvm_round3/boot2/quality.json；完整 dmesg 已保存。

2026-11-03T20:13:54.983171+08:00 第三轮两次 LLVM memcheck 均身份/cmdline 有效且 STATUS=DONE、三份 smaps gzip 完整，原静止判定均 steady=no；boot1 ELF tar 不完整并有 gzip SIGABRT，boot2 按补充指示执行原版完整第 6 步且 ELF tar 完整、所存完整 dmesg 未见 gzip 信号。boot2 没有复用 boot1 无效归档。四次开机原逐次采样按内存单独条件最早达标 uptime：GCC boot1=1080s、boot2=839s，新 LLVM boot1=779s、boot2=628s；到 uptime 约2700s 的 MemAvailable/Swap 变化已保存 analysis/memory_only_earliest_to_45min.tsv。SwapCached 和 Slab 未逐次采样，无法回算该区间变化量，未改板上静止逻辑。

2026-11-03T20:13:55.008013+08:00 第三轮四开机初步重算：smaps_rollup 的 Pss+SwapPss LLVM3−GCC 均值=-12042.5 kB，小于 GCC/LLVM3 开机极差 17742/8289 kB；GCC 非 PIE 15 路径组 +10414 kB（极差168/108），GCC 预链接而新 LLVM 无标记库逐映射 Private_Dirty +14232 kB（极差1824/1320），后二者超两侧极差，互有重叠不能相加。同路径、第三轮 clang 标记对象代码段逐映射 Pss +5292.5 kB（极差1449/34），不能直接归因 -Os。来源 data/llvm_round3/analysis/ 下四开机 TSV 与原始快照。

2026-11-03T20:16:08.060118+08:00 boot3 已重启，身份通过；cmdline有效性=True。证据 data/llvm_round3/boot3/latest_boot.json

2026-11-03T22:26:33.169127+08:00 第三轮 TPMS 默认全套结束，原始结果和独立默认数据库见 data/llvm_round3/boot3/tpms/；失败用例补测与恢复尚待完成。

2026-11-03T23:53:31.640784+08:00 TPMS 单独补测结束，原始结果与独立数据库见 data/llvm_round3/boot3/tpms/quality_retry；恢复清理待执行。

2026-11-04T00:02:56.173547+08:00 第三轮板子最终恢复完成：Dali 包管理注册残留经备份和逐表审核后定点清理；最终重启后原设置、RPM/应用/cyad、原文件属性与关键挂载点均匹配部署前基线，本轮目录已清理，sdb root off 后 uid=5001。证据 data/llvm_round3/cleanup/summary.json。

第三轮结果收口：两次新 LLVM memcheck 的身份、排除 blperf 后 cmdline、STATUS=DONE 与三份 smaps gzip 均有效；原 CPU<20% 静止判定两次均未通过，因此所有空闲内存差值须带此限制。boot1 ELF tar 被 gzip SIGABRT 截断，boot2 按原第 6 步重跑并通过 tar/gzip 校验，**boot2 的 ELF 数据未复用 boot1**。四开机“只看内存”最早达标 uptime 为 GCC 1080/839 s、新 LLVM 779/628 s；到约 2700 s 的 MemAvailable 变化依次为 +1152/-3840/-2496/+3568 kB，Swap 已用变化依次为 0/-3584/-808/-9380 kB。逐次记录未包含 SwapCached、Slab，无法计算所求同区间变化；本轮未修改静止条件。来源 analysis/memory_only_earliest_to_45min.tsv 与报告。

第三轮 TPMS 默认全套 16 项按原顺序执行，默认 DB 155 行且完整性通过。Dali 原始 enlightenment_info 为 0 字节、DB 失败；FFmpeg 4 配置中 3 个不足五个有效样本（HEVC 两项均 0），其阶段 dmesg 有 ffmpeg SIGABRT；GStreamer 虽有四项数值样本，阶段 dmesg 有 gst-launch-1.0 SIGABRT；dotnet 默认方法/DB 失败，远端作业保留 DONE/rc=0 与传输层 LOST_WORKER 并存证据。独立 quality_retry DB 31 行且完整性通过：Dali 仍 0 字节/失败，HEVC 仍无有效样本且 ffmpeg SIGABRT 复现，gst-launch-1.0 SIGABRT 复现，dotnet 方法与 DB 成功。默认数据未被补测替换。分析见 analysis/tpms_case_quality.json、signal_coverage.json 与 reports/round3_attribution.md。

第三轮最终归因：smaps_rollup 用户态 Pss+SwapPss 新 LLVM−GCC=-12042.5 kB，低于 GCC 17742 kB 开机极差；GCC 非 PIE 15 路径组 +10414 kB、GCC 已预链接而新 LLVM 无标记库逐映射私有脏页 +14232 kB，均超两侧极差且两个视角不能相加。由原始逐映射独立重算的预链接私脏差为 +14258 kB，作为当前可识别恢复上限；同路径 clang 标记代码段 Pss 是 +5292.5 kB，未见代码段收益。新 LLVM 默认 TPMS IdleMemoryUsage=488 MB，GCC=488 MB，同一时刻 swap 已用为 136720/141640 kB；单次 TPMS 差受历史同 LLVM 约 51 MB Idle、75 MB ProcessPSS 波动限制。rpi4 在本地相关文本和保留 DB 中未找到可追溯的三次原始运行，已列复测材料。完整来源、噪声与优化风险见 reports/round3_attribution.md；板上恢复及本地最终审计见 cleanup/summary.json、analysis/final_audit.json。最终本地提交与复核分卷待生成。

2026-11-04T01:49:48.027908+08:00 第三轮交付完成核对：最终审计 analysis/final_audit.json 通过；报告 reports/round3_attribution.md 已生成；本地 memdiff 分支已完成数据/报告/STATUS 首次完整提交 948637a190ef154d905ac79a34e1b0af590d8ea6，未 push。纯文本复核材料 review_txt_round3/ 已生成 2 卷且均小于 4,000,000 字节；mapping_path_segment_four_boots.tsv 在文本分卷按首 2000 行截断，仓库完整 TSV 保留。板子最终重启与清理状态仍以 cleanup/summary.json 为准。本条作为收尾状态补充提交。

### 第三轮补充：预链接进程分层、静态 ELF 与服务只读复核（2026-11-04）

计划与范围：本机只复用 GCC/LLVM3 各两次 `02_steady/smaps_raw.txt.gz`、`classification.json` 中 410 库/15 程序及两侧已拉回 ELF 和保存的 GBS 交叉 readelf 输出；板上只做身份核对、指定 systemd 单元/路径/引用字符串/dlog 的只读检查，不重启、不改设置或文件。新脚本 `scripts/round3b_*.py`；本机中间表存 `data/llvm_round3/analysis/round3b_*`，板上原始输出与逐命令返回码存 `data/llvm_round3/service_followup2/`，结论追加 `reports/round3_attribution.md` 第十节，并修订第五、八节。

已闭合的测量：410 库 `r--` 私有脏页四次开机为 GCC 60880/60504、LLVM3 75752/75444 kB，LLVM−GCC 均值差 +14906 kB，两侧极差 376/308 kB。按进程可执行路径优先归 GCC 非 PIE 15 目标、再按 smaps 中映射的 `/usr/bin/{launchpad-loader,app-defined-loader,dotnet-loader,dotnet-hydra-loader,wrt-loader,launchpad-process-pool}` 归加载器组、最后归其余组：三组净差分别 +8988、+18、+5900 kB；15 组占净差 60.3%，加载器组 +18 未超过 GCC 极差 28。15 组内另有 +2140 kB 来自映射了加载器路径的目标进程；若采用非互斥的所有加载器映射进程口径为 +2158 kB，与 15 组重叠，不能相加。仅两边都有的 15 目标程序路径逐项正差之和为 9204 kB，是定点关 PIE 对本组只读私脏的可识别观测上界，**不是可得收益**；整池 +14906 kB 不能记给定点方案。完整四值/均值/极差、逐进程与逐库数据见 `analysis/round3b_prelink_groups_four_boots.tsv`、`analysis/round3b_prelink_process_segment_four_boots.tsv`、`analysis/round3b_prelink_library_segment_four_boots.tsv`、`analysis/round3b_prelink_process_summary.json`；四份原始 gzip 路径在 summary JSON 中。

已闭合的静态量：GCC 410 库和 15 程序附件齐全；LLVM3 410 库齐全、15 程序中未运行的 acm-service ELF 未拉回，故程序差值限于 14 对。410 库的 LLVM−GCC `.text` 为 -8233300、`.data` -86094、`.bss` +129012、`.data.rel.ro` +122668、`.got` +93540、RELRO +106496 字节；动态重定位合计 +32104 条，其中 R_ARM_RELATIVE -12225、R_ARM_GLOB_DAT -8158、R_ARM_JUMP_SLOT +21873、R_ARM_ABS32 +30553。14 对程序的同口径总量与前 30 对象在 `analysis/round3b_static_elf_totals.tsv`、`analysis/round3b_static_elf_top30.tsv`；逐对象原始 ELF/readelf 路径在 `analysis/round3b_static_elf_objects.tsv`。GCC 附件没有缺项，无需调用第二轮 RPM 解包回退。RELRO 和 R_ARM_RELATIVE 已逐项与原 `elf_stats.tsv` 核对。

归因边界：410 库中有 242 个重定位总数或 RELRO 增长，与 +11014 kB 只读私脏净差共现；另 168 个两项静态量都未增长，仍有 +3892 kB 净差。共现量不是静态增长的因果解释量，因预链接标记也同时变化；本轮不能把 14906 kB 在两机制间唯一分摊。来源 `analysis/round3b_reloc_relro_vs_dirty.tsv`、`analysis/round3b_static_elf_summary.json`。优化清单修订存 `analysis/round3b_optimization_revision.tsv`：代码段和 zram 是理论池上限、不排序；代码段基本不反映在 TPMS Used (Mem)，因为文件映射代码页可回收并计入可用内存估计。

板上只读复核：四项身份检查通过（`service_followup2/identity_checks.json`），`systemctl cat` 两个指定单元均 rc=0；acm `.path` 仅监视 `PathExists=/opt/usr/apps/MCS_mode`，该路径当前不存在（`test -e` rc=1）；networkspeaker `.busname` 指向 acm service。指定字符串在限定目录里命中 acm-service、acm-watcher 和三份 acm 相关库；perception appid 在可读文件里未命中，但 `grep` rc=2，包含 182 条失效符号链接及 `/usr/apps/dpm/plugins` 权限拒绝，不能证明全镜像无引用。来源 `service_followup2/references.json`、`monitored_paths.json`、`raw/systemctl_cat_*.stdout`、`raw/grep_*.stdout`。root UID 0 下 dlogutil main/system 均 rc=0，但各只有 9 行工具诊断、实际事件 0 行，未满足每个缓冲区 >10 行的验收条件；原 journal 为空、原 dlog 仅环形缓冲区说明行，两次都属于日志采集未成功，不能写成“没有失败证据”。perception-engine、acm-service 结论均改“原因未查明”。来源 `service_followup2/dlog_quality.json` 和原始输出。末次 `sdb root off` rc=0，UID 5001；所有板上命令返回码见 `service_followup2/commands.json`。未重启、未拉起或停止服务，板上无本轮文件或设置变更。

挂账：perception/acm 缺席原因仍需有效的启动日志与触发条件证据；`/usr/apps/dpm/plugins` 无读取权限，限定范围搜索不完整；LLVM3 acm-service ELF 附件缺失，程序静态合计只能做 14 对；预链接与重定位/RELRO 对私脏的独立因果份额需用户和 Claude 设计单变量对照实验。本补充仅测量和分析，未实施构建改动。

### 第三轮补充二：预链接装载地址、页模型与启动链（2026-11-04）

计划与执行：仅复用 GCC/LLVM3 各两次 `02_steady/smaps_raw.txt.gz`、410 个已分类库的保存 ELF/readelf 输出；脚本 `scripts/round3c_model.py`、`round3c_scenarios.py`。逐进程×库装载地址、4KB RELRO 页类别、模型和敏感性中间表保存在 `data/llvm_round3/analysis/round3c_*`。板上按四项身份检查后只读查 systemd 单元、MCS_mode/perception 引用、vlog 和 sqlite，只读原文及逐命令返回码保存在 `data/llvm_round3/service_followup3/`，未重启、未创建或修改板上文件，最终 `sdb root off` rc=0、UID 5001。结论详见 `reports/round3_attribution.md` 的“第三轮补充二”。

装载地址验证：GCC boot1/2 的 15 个非 PIE 目标程序进程中，各 2133/2194（97.22%）个库×进程映射位于 ELF 预链接地址，仍有 4168 kB `r--` 私有脏页；其余进程分别 989/9817（10.07%）、989/9742（10.15%）位于预链接地址，不在地址的映射产生 54332/53956 kB 只读私脏。因此“PIE 进程里的 GCC 库也普遍在预链接地址”不成立，“非 PIE 组接近 0 脏页”也不成立。逐条来源 `analysis/round3c_process_library_model.tsv`、汇总 `analysis/round3c_gcc_load_address_summary.tsv`；410 库 GCC/LLVM3 ELF 均齐全，`analysis/round3c_missing_elf.tsv` 为空。

页模型：GCC 410 库 GNU_RELRO 页分为无重定位 110、仅 RELATIVE 369、含非 RELATIVE 257；LLVM3 对应 9/339/307 页。按任务指定公式，GCC boot1/2 全量预测比实测低 900/904 kB（1.48/1.49%），LLVM3 高 2724/2728 kB（3.60/3.62%），但 GCC 15 组低 4168 kB（93.5%），已如实报告超过 20% 的失配。若强制假设 LLVM 所有库恢复后均加载在预链接地址，预测相对 GCC 实测 −34616/−34376 kB，均值 −34496 kB；这一假设与 GCC 其余进程约九成映射不在预链接地址的实测矛盾，不能作为可信可得收益。按 GCC 同库同组实际装载比例的敏感性模型给出 +409/+497 kB（仍采用 15 组零页假设）；若允许 15 组按符号重定位页写脏，则 +6036/+6123 kB。模型表 `analysis/round3c_model_aggregate.tsv`、`round3c_restoration_scenarios_summary.tsv`；前 30 库及类型/进程数 `round3c_top30_symbol_page_growth.tsv`。两边 glibc 包为 GCC 2.40-1.12、LLVM3 2.40-1.72；本地/GBS root 未找到对应 `do-rel.h`，Tizen 源站不可访问，未核实镜像所用的具体代码，见 `analysis/round3c_glibc_source_check.json`。

服务只读复核：MCS-starter.target 当前 inactive/dead，status rc=3，`show` rc=0；MCS-starter.path 监视 `/opt/usr/apps/MCS_mode`，该路径当前不存在（test rc=1）。`/usr/lib/systemd/system` 里匹配 bootseq/MCS 的 44 个单元均保存完整 `systemctl cat`；MCS_mode 在指定目录命中 11 路径，perception appid 命中 19 路径（应用自身、配置、数据库等），但没有确证它的启动调用方，grep 有失效链接且 `/usr/apps/dpm/plugins` 权限拒绝。只读包管理库记录 perception `onboot=false`、`autorestart=true`、`preload=true`、background_category=0；metadata 为 background-update=inactive、built-in-app=true，所查 app-control/category/boot_sequence 为空。vlogutil 最近 600 秒实际日志 245122 行、过滤 5754 行，采集成功；窗口在开机数小时后且含本轮 sdb 命令，不能推断启动阶段。来源 `service_followup3/target_status.json`、`related_units.json`、`references.json`、`sqlite_followup_queries.json`、`vlog_quality.json`、`commands.json`。

挂账：任务指定的全库在预链接地址假设及 15 组零脏假设已被 GCC 运行数据否定；恢复预链接后的实际结果需控制加载位置、进程集合和 glibc 补丁的实验验证。Tizen 对应 `do-rel.h` 未取得，不能据上游源码断定此镜像实现；perception/acm 缺席原因仍未查明。板上搜索权限不足路径仍需有权限的独立复核。

### 第三轮补充三：RELRO 按符号重定位与一次重启日志（2026-11-04）

计划与执行：只用上一轮前 30 库及指定补充库去重后的 31 库，两侧已拉回 ELF、保存的交叉 readelf 重定位输出，并用同一 GBS 交叉 readelf 读取两侧 `.dynsym/.symtab`；不重编。脚本 `scripts/round3d_symbol_relocations.py`，完整逐重定位和逐库中间表保存在 `data/llvm_round3/analysis/round3d_*`，报告追加 `reports/round3_attribution.md`“第三轮补充三”。板上四项身份检查前后均通过，root 下按第三轮原路径实际重启一次，uptime 约 285 秒抓 `vlogutil -t 315`；原文、筛选、进程计数和逐命令返回码在 `data/llvm_round3/service_followup4/`。最终 `sdb root off` rc=0、UID 5001，无本轮板上文件或设置残留。

闭合的符号统计：31 库 RELRO 内 `R_ARM_ABS32/R_ARM_GLOB_DAT` 逐条目标按 ELF32 `r_info>>8` 索引 `.dynsym`，GCC a/b/c/d 为 2491/0/4200/0，LLVM3 为 10530/0/9665/0。a 是本库定义、GLOBAL/WEAK、DEFAULT；b 是本库定义、隐藏或受保护；c 是未定义外部；d 是其它。LLVM3 a 类的 10530 条中，7858 条同名符号在 GCC `.dynsym` 有定义；2672 条在 GCC `.dynsym` 未找到。两侧 31 库均无 `.symtab`，因此不能验证只存在 `.symtab` 的 LTO 内部化。两边各有 4 库带 DT_FLAGS SYMBOLIC 和 DT_SYMBOLIC，见 `analysis/round3d_symbol_object_summary.tsv`。完整 26886 条见 `analysis/round3d_relro_symbol_relocations.tsv`，交叉 readelf 符号输出及 ELF SHA 在逐库表追溯。

按 LLVM3 两次开机的每库映射进程数均值加权，a 类去重 RELRO 4KB 页理论上界 **5476 kB**，a+b 并集仍 **5476 kB**（b=0）；GCC 同口径为 1324/1324 kB。此为兼容的装载/预链接状态下上界，不是直接可得收益：当前 LLVM 无预链接，把 a 转成 RELATIVE 仍可能写脏，且同页其它重定位仍在。来源 `analysis/round3d_symbol_page_bounds.tsv`、`round3d_symbol_summary.json`。a 占比最高五库为 libsqlite3、libxml2、libeo、libjpeg、libefl；仅从保存包清单得到候选包名，工作区无对应 spec/build.conf/LTO 清单，GBS local/sources 空且 Tizen spec URL 超时，因此其实际构建系统、-fvisibility=hidden、GCC LTO 成员资格均记“未找到”，见 `analysis/round3d_top5_build_lookup.tsv`。

重启日志：顶层 `sdb reboot` 不受支持、非 root shell `reboot` 不在 PATH，两次失败未改变 boot ID，原始证据保存在 `service_followup4/attempt0_unsupported_sdb_reboot/`、`attempt1_unprivileged_reboot/`；随后 root shell `reboot` 成功，boot ID `d040aa29-3dd2-4aea-95a7-79f3f33ecc07`→`8ccfe898-8ebe-4900-9db7-a35cb718fe5d`。原始 vlog 233555 行、可识别事件 203131 行，最早 uptime 38.648 秒，**没有 0–30 秒日志**；头部显示 `vlog_size(32)`、`Logging Time 38.640~285.583`，推断早期日志被 32 MB 环形缓冲区覆盖。过滤去重后 2328 行：perception 0、acm 504；acm-watcher 在 74 秒记录“无节点→正常 _exit(0)→socket 再触发”，`ps` 仅见 acm-watcher，MCS_mode 不存在。没有覆盖开机前 38.6 秒，因此仍不能判定 perception-engine 或 acm-service 的完整启动原因。来源 `service_followup4/capture.json`、`vlog_filter_summary.json`、`vlog_filtered_unique.txt`、`commands.json`；原始 vlog 仅在 `service_followup4/raw/vlog_full_boot.stdout`，不进入复核分卷。

挂账：五个库的实际包构建 spec 和 GCC LTO 清单不可得；Tizen glibc 实际补丁仍未核实。两服务缺席的完整启动过程仍受最早 38.6 秒 vlog 缺口限制，不能把本轮零条 perception 关键字解读为未尝试启动。页数加权上界需要控制符号绑定、预链接与装载位置的实验才可转为收益估计。

### 第三轮补充：四库板上 prelink 改写核查（2026-11-04）

计划与进度：本机使用保存的 GCC/LLVM3 四库板上 ELF、用户给出的四库 RPM 原件重定位计数及第三轮平台 readelf；不访问开发板。按用户更正，仅从指定公开 Tizen Base 快照与 ftp.gnu.org 下载 glibc 2.40 源码，在仓库外按 spec 顺序应用补丁并与上游对照。分析脚本 `scripts/round3e_prelink_rewrite.py` 已完成，八份 `readelf -W -S -l -d -r -s` 和八份 `.comment` 输出及逐命令 rc/stderr 存 `data/llvm_round3/analysis/round3e_readelf/{GCC,LLVM}/`；全部 rc=0。全节/动态项/逐节×类型/目标区域/原件差值/十条符号对齐/amd 导出差集均已落表。报告为仓库根目录 `docs/round3e_prelink_rewrite.md`，本次只标记旧结论、不重算 410 库。

已闭合：GCC 板上 libecore、libecore_con、libelementary 相对用户给的未预链接 RPM 原件分别少 434/564/4488 条 ABS32，并恰好多同数 GLOB_DAT；四类重定位总数、RELATIVE 和 JUMP_SLOT 均不变，没有 `.gnu.conflict` 承接。libamd 四类数值不变，但 GCC 板上 `.rel.dyn` 节类型为 RELA，动态项为 `RELA`/`RELASZ`/`RELACOUNT`。GCC 四库都有 `.gnu.liblist` / `.gnu.prelink_undo` 节及 `GNU_PRELINKED` / `CHECKSUM`；LLVM 副本无。十条 libecore 同名、同符号归属且一对一的 LLVM ABS32 在 GCC 副本均为 GLOB_DAT；两边节布局不同，不能证实同一源对象槽位。证据 `round3e_readelf/original_vs_board.tsv`、`sections.tsv`、`dynamic_tags.tsv`、`ecore_10_symbol_alignment.tsv`。

运行时限定：其余进程约 10% 库映射位于预链接地址、仍有 +5900 kB `r--` 私脏差是原 smaps 观测；不能用普遍 `l_addr==0` 解释。四库 r-- 私脏净差 +1028 kB，rw- 为 -268 kB，提示只看 r-- 会混入目标区域转移；还不能定量归因 prelink。libamd 板上导出 365/672，LLVM 独有 316（按前缀分组在 `libamd_llvm_only_prefix_counts.tsv`）；两边 JUMP_SLOT 611/885 与用户原件相同。报告第三节逐项标记 +32104、ABS32 +30553、GLOB_DAT -8158、round3c 0.4–6.1MB、round3d 5476kB/top5 等的有效边界，未改旧报告原始数值。

挂账：四份 RPM 原件 ELF 未提供，只有用户给出的类型计数，不能逐偏移证明改写或原件目标页。公开 glibc-2.40-16.8 不一定是 VD 镜像的 glibc-2.40-1.12/1.72；请用户在内网核对 VD spec 版本与全部补丁，尤其与公开 `Patch0 d7477af-to-afd8935.diff.gz` 对照。公开 ARM 源码不执行 libamd 的 RELA 条目；prelink 是否已预填及 VD loader 是否另有补丁仍需核对。410 库静态归因与恢复预链接反事实仍需要两边全部 RPM 原件及受控样本，由用户与 Claude 决定后续。

源码核查已闭合（公开快照范围）：下载 `glibc-2.40-16.8.src.rpm`（SHA256 `3105a7bd9ee2afe03341fc7eca3d7ce61544bd945eba4f48afee3e7894e67161`）；spec 仅含 `Patch0 d7477af-to-afd8935.diff.gz`，按 `%prep` 顺序应用成功。打补丁后的 `elf/do-rel.h`、`elf/dl-reloc.c`、`sysdeps/arm/dl-machine.h` 与 GNU glibc 2.40 原文逐字节相同。普通 ARM REL 在 `l_addr==0` 时只跳过 `DT_RELCOUNT` 覆盖的 RELATIVE，ABS32/GLOB_DAT 仍处理；`l_addr!=0` 时 RELATIVE 也处理。公开 ARM 声明 `ELF_MACHINE_NO_RELA=1`，不执行板上 libamd 的 RELA 条目；可能由 prelink 预填，不能外推为 VD 实际行为。证据 `data/llvm_round3/analysis/round3e_readelf/tizen_glibc_source_provenance.json`、`tizen_glibc_source_line_evidence.txt` 和 `docs/round3e_prelink_rewrite.md` 第二节。

### 第三轮补充：VD glibc 源码与其余进程拆分（round3f，2026-11-04）

计划与进度：本机只读复核用户提供的 VD GCC/LLVM 两侧 glibc 打补丁源码摘录、round3d 生成代码，以及已保存的四次开机 smaps/ps/ELF 统计；未访问开发板或网络。两份材料已从 `/home/linhao/Downloads` 移动到 `docs/evidence/vd_glibc/`，Downloads 下无副本；`vd_glibc_src.txt` SHA256 `9b2018c0ba6a36f937507eeb26b997edfce123ce556d0a47aa4f823ad4d0eb72`，`vd_glibc_excerpt.txt` SHA256 `441df8d23653221408686767ada7f1d4e24e482a8f78857d2cafe375761efac5`。报告 `docs/round3f_vd_glibc_and_process_split.md` 取代 round3e 第二节的公开 glibc 运行时解释；旧报告首页已加指向新报告的提示。分析脚本 `scripts/round3f_process_split.py` 在 nice/ionice 下完成，进度与“已结束”状态见 `data/llvm_round3/analysis/round3f_process_split.log`。

已闭合：VD `rtld.c:2297–2404,2434–2469` 先对整程序比较 liblist/顺序/地址/checksum/时间戳，成功后只处理冲突项并标记全库已重定位；失败才进入普通重定位。VD ARM 普通 REL 的 `do-rel.h:115,121` 在同址时跳过相对快路径；`124` 的 GNU_PRELINKED 条件只在 RELA 分支。VD `dl-machine-rel.h:25–27` 保留正常 loader 的 RELA 支持，解释公开 Tizen 源码不能外推 libamd。1009 恢复 LD_USE_LOAD_BIAS 默认：非 PIE 主程序保留库首选地址、PIE 不保留，与 round3c 97.22% 对约 10% 的方向吻合；1010 增加诊断与 `vdprelink` 失败退出，不改变成功判定条件。证据 `docs/evidence/vd_glibc/`、`round3f_source_material_audit.json`、`round3c_gcc_load_address_summary.tsv`、报告第一节。

round3d 指标已核代码：`RELRO_ABS32_GLOB_DAT_count` 为指定重定位节中目标偏移落 GNU_RELRO 的 ABS32/GLOB_DAT 条数，并非所有 GLOB_DAT 或只算 a 类；GCC ecore/con 的 699/958 条 GLOB_DAT 均在普通可写段，故指标为零。LLVM 5476 kB 仍是当前 a 类页×映射进程的静态上界，不能当成恢复预链接可得收益；top5 仅是 a 占比排序。证据 `scripts/round3d_symbol_relocations.py:19–21,72–96,153–172,201–243`、`analysis/round3e_readelf/relocation_by_region_type.tsv`、报告第二节。

其余进程 410 库 `r--` 私脏净差 +5900 kB：前五正差项合计 +4444 kB；前 30 项 +6860 kB、其外净 −960 kB。可确认“由非 PIE loader 派生且未重新 exec”进程为 0，故贡献 0/5900；其 GCC 同址映射比例为 0/0、无定义。已 exec 的可见 loader 后代净差 +136 kB，GCC 同址映射 0/4662。四次逐 PID、按进程名+主程序路径配对、前 30 和来源见 `analysis/round3f_process_rows.tsv`、`round3f_process_name_pairs.tsv`、`round3f_top30_remaining_processes.tsv`、`round3f_process_split_summary.json`。本次只计算现存快照，不据此推断 prelink 单变量收益。

挂账：材料不含 1008 补丁全文、连续 `rtld.c:2297–2395` 或 `dynamic-link.h` 完整传参宏；1010 全文和关键源码摘录足以支持本篇限定结论，但缺失部分已在报告列明。GCC Base 源码包 `2.40-10.46` 与旧板上清单 `2.40-1.12` 的身份链仍须内网核对。快照未保存进程历史祖先、环境变量或启动时 prelink 校验日志；剩余 5900 kB 不能按原因唯一归属。板上验证命令仅列在报告，未执行。


### 第三轮补充：410 库剩余差额和链接属性（round3g，2026-11-04）

计划与进度：本机只读重算 GCC/LLVM3 各两次 `02_steady/smaps_raw.txt.gz`；按 15 个 GCC 非 PIE 程序进程与其余进程分组，统一用 410 库文件映射 `r--+rw-` Private_Dirty，并列旧 `r--`。同名同 `/proc/PID/exe` 路径在四次快照均存在才纳入严格配对。另按相同路径配对两侧保存的 ELF，复用第三轮平台交叉 readelf 原始输出，查 NEEDED、GNU_RELRO、保存的 rpmdb 包名；未访问开发板、未重编或改配置。报告 `docs/round3g_residual_split.md`；脚本 `memdiff/scripts/round3g_residual_split.py`、`round3g_linker_flags_audit.py`；完整中间表、JSON 和有结束状态的运行日志见 `memdiff/data/llvm_round3/analysis/round3g_*`。

已闭合的实测：旧 `r--` 两组 +8,988/+5,918 kB（旧三组“其余” +5,900 kB，另有加载器组 +18）；新 `r--+rw-` 两组 +9,452/+4,806 kB，总 +14,258 kB。其余组剔除只在一侧的进程为 +4,888 kB，严格四次均在的进程为 +4,856 kB。前十可配对进程净 +5,024 kB：只在一侧加载的库净 +20、同库未能定因 +5,004；同址 RELATIVE-only 的 GCC 板上预链接副本静态代理上界 5,352 kB，不等于实测节省。证据 `round3g_two_group_totals.tsv`、`round3g_process_presence_and_delta.tsv`、`round3g_focus_library_detail.tsv`、`round3g_focus_attribution.tsv`。

链接属性：两侧保存 ELF 1,463/1,403，相同路径 1,377；466 个配对 ELF 在 LLVM 侧有额外 NEEDED，4 个 GCC 有而 LLVM 无 GNU_RELRO，不能配对 112 个路径。前十进程中额外 NEEDED 与 LLVM 独有映射库同名候选去重后私脏 +20 kB，已计入前述库集合项；尚无证据证实因 `--as-needed` 丢失而加载。包名从保存的 rpmdb 查询，候选中各侧 44 个路径未找到所有者。证据 `round3g_elf_needed_pairs.tsv`、`round3g_elf_lost_relro.tsv`、`round3g_extra_needed_process_hits.tsv`、`round3g_linker_candidate_rpm_owners.tsv`。用户内网确认 GCC/LLVM 的 rpm 链接选项由 optflags 移至 build_ldflags；具体包是否漏传需核对 spec 和最终链接命令。

挂账：缺两侧 410 库 RPM 原件逐页重定位偏移及受控运行时写页证据，前十同库 +5,004 kB 不能分成预链接、页面布局和运行时初始化。ELF 仅按相同路径配对，跨路径版本和保存 rpmdb 未登记的 /opt/usr/apps 文件无法定包；附表列出待核查项，后续需由用户/Claude 设计实验。


### 第三轮补充：匿名内存严格配对与 PIE 落址上界（round3h，2026-11-04）

计划与进度：只在本机离线读取 GCC/LLVM3 各两次保存的 `02_steady/smaps_raw.txt.gz`、round3g 同名同主程序路径进程键、round3c 库落址表及已保存 GCC 预链接 ELF 的平台 readelf；未使用开发板、未采集或联网。脚本 `memdiff/scripts/round3h_beyond_gcc.py`，报告 `docs/round3h_beyond_gcc_levers.md`，中间表和有“已结束”成功记录的日志在 `memdiff/data/llvm_round3/analysis/round3h_*`。逐映射匿名 Pss/SwapPss/Private_Dirty 四次总数均与既有 `mapping_source_four_boots.tsv` 完全一致。

已闭合的实测：全系统匿名 Pss+SwapPss LLVM−GCC 为 −18,160 kB；严格四次均存在的进程 −10,173 kB、单侧进程 −7,911 kB、跨镜像存在但有一次缺席 −76 kB。严格配对总差没有超过 GCC 10,941 kB 开机极差，因此按既定判据可确认的“严格配对总体优势”为 0 kB。49 个逐进程差额超过两侧各自极差，净差 −3,274 kB（负差总量 3,858 kB），不可替代总体判定。主要单侧贡献为 GCC 独有 perception-engine −6,917、acm-service −1,700，LLVM 独有 bnr-service +706 kB；进程集合差不能称为编译器效应。证据 `round3h_anonymous_groups.tsv`、`round3h_anonymous_process_deltas.tsv`、`round3h_anonymous_top20_each_direction.tsv`。

GCC PIE 进程中，未落在预链接地址的 410 库按已预链接 GCC 板上 ELF 的 RELATIVE-only 可写文件页法，上界为 boot1 46,420、boot2 46,136 kB；已同址部分两次均 5,356 kB，总候选页池 51,776/51,492 kB。此为静态理论上界，不是实测节省，不能抵扣 round3g 其余进程 +4,806 kB 私脏差或推断 LLVM 恢复预链接后的效益。证据 `round3h_pie_library_address_bound.tsv`、`round3h_pie_address_summary.tsv`、`round3g_two_group_totals.tsv`。

挂账：既有快照没有保存准确线程数，逐进程编译来源/VMA 表明确标 `NOT_CAPTURED`，栈 VMA 数不当作线程数；单进程匿名内存差仍可能来自工作负载。LD_USE_LOAD_BIAS=1、整程序 prelink 成功率、地址冲突回退、安全影响与实际内存收益均需由用户和 Claude 设计实验镜像验证，本轮只列步骤，不执行。


### 关 PIE 实验测量方案补充：线程/栈与加载偏置第二阶段（2026-11-04）

计划与进度：本次只修改方案和新脚本并在本机离线演练，无开发板访问、采新数据、联网或配置实施。新增 `docs/nopie_experiment_plan.md`，规定普查及每次 memcheck `02_steady` 稳定点抓 `/proc/PID/status:Threads` 与逐线程栈 VMA Pss/SwapPss/Private_Dirty；第二阶段同一关 PIE 镜像无/有 `LD_USE_LOAD_BIAS=1` 各两次开机，以两边开机极差判定，提供全局 systemd 默认环境和逐服务 drop-in 两种临时方案及恢复核对。脚本 `memdiff/scripts/nopie_capture_threads.sh`、`nopie_compare.py`、`nopie_stage2_load_bias.sh`、`nopie_stage2_metrics.py`、`nopie_service_health.sh`；均未上板执行。

离线演练闭合：第三轮 LLVM boot1/boot2 及其 GCC 基线保存的四份 smaps 重新解析出栈 VMA 1043/1031/993/982 行，严格配对 249 进程键栈 Pss+SwapPss 差 −5978 kB，与 round3h 一致。线程数差、每线程平均栈 Pss 两列成功出表，但旧快照无 `/proc/PID/status`，249 键真实线程数均标 `NOT_CAPTURED`，不可推断 −5978 kB 原因。第三轮 LLVM 两次单快照指标复算：PIE 的 410 库同址映射 0/11814、0/11756；410 库 `r--+rw-` 私有脏页 87692/86344 kB、匿名 Pss+SwapPss 171579/171852 kB，与旧结果一致。把同一两次 LLVM 数据自比对，六项指标差均为 0，仅验证管线，不是变量效果。证据 `memdiff/data/llvm_round3/analysis/nopie_rehearsal_20261104/`、`nopie_rehearsal*.log`。脚本通过 bash 语法、Python 编译及合成线程样本数值检查。

挂账：`LD_USE_LOAD_BIAS=1` 仍未实验；VD glibc 安全分支源码会解析该变量、unsecvars.h 又列出清理项，实际 AT_SECURE 效果需在实验镜像验证。上板前需用户决定安全团队评估、全局或逐服务方案、需排除的服务（尤其对外服务）。测后必须按方案恢复原文件和 SHA、重启核对并清理临时目录；预计第二阶段约 2.5–3 小时，不含第一阶段时间。

### 关 PIE 实验方案修订：21%/30 分钟、实例普查与放行（2026-11-05）

计划与进度：按用户当前决定，仅修订 `docs/nopie_experiment_plan.md` 和实验脚本，本机离线重放第三轮旧数据；未访问开发板、未更改板上设置。原 `memdiff/scripts/memcheck_runtime.sh` SHA256 为 `8070e97a9ca788bb89d0c514dfa1fc76d064752c5e44b34962f8127a98c3a723`，保持不变。`nopie_prepare_payload.py` 生成独立 `nopie_memcheck_payload.sh`，将前台/后台入口指向实验副本，仅将采集判定的 CPU 平均忙碌率 `<20%` 改为 `≤21%`、等待上限 2700 秒改为 1800 秒；保留 30 秒采样、10 次窗口和内存阈值。新 `steady_quality.tsv` 记录实际采集开机秒数、CPU 条件、超时原因和只看内存最早达标时刻。生成副本哈希见 `nopie_payload_provenance.json`。

已闭合演练：旧 LLVM3 boot1/boot2 保存的逐次采样重放后，新规则首次满足完整静止判定为开机 899/869 秒；只看内存首次满足为 479/418 秒。见 `analysis/nopie_policy_rehearsal.tsv` 和日志。第一阶段放行脚本 `nopie_survey_gate.py` 对旧 LLVM3 判定“不进入测量阶段”：15 目标 EXEC 0/15、DT_GNU_LIBLIST 0/15、410 库 GNU_PRELINKED 0/410；强制模式先写证据再以退出码 2 阻止测量。证据 `analysis/nopie_rehearsal_20261105/gate_enforced/gate_result.json`、`analysis/nopie_gate_enforced_20261105.log`。`nopie_stage2_metrics.py` 新输出全部进程的库落址表，旧 LLVM3 目标进程同址 0/2033；本机重复解析的表和日志见 `analysis/nopie_rehearsal_20261105/`。

systemd 实例：新 `nopie_capture_instances.sh` 为未来普查记录每个进程 cgroup 与父进程链；旧数据只见七个重点 PIE 进程 PPID=1，没有 cgroup，全部“待普查确认”。证据 `analysis/nopie_focus_instance_rehearsal.tsv`。第二阶段方案按用户决定采用系统级和用户级全局 `DefaultEnvironment`；`nopie_stage2_load_bias.sh` 分别对两处 drop-in 做原文件 SHA 备份、应用、重启验证、恢复、重启复核。`mount-check` 记录 `/`、`/etc` 和目标目录挂载选项，只读时需显式 `remount-rw`，完成后 `restore-mounts` 恢复原选项并复核，目标不可写时停止且不改用 `/run`。本轮只通过 shell 语法检查，未对开发板执行 remount 或 drop-in。

对比限制与挂账：410 库 `r--+rw-` 私脏及 15/其余组差额可并列 GCC、旧 LLVM3 基线及采集时刻；匿名、SwapPss、zram、文件缓存、MemAvailable 因新采集点约 30 分钟以内，只在同一实验镜像两阶段比较，跨镜像须标“采集时刻不同，不作结论”。实验先只在开发板开展，不涉及产品；安全评估待实测收益后开展；实验全局覆盖 system/user 且不排除服务，产品阶段再考虑排除对外联网和特权服务。真实实验镜像身份、cgroup、15 程序的 ELF 与 GNU_LIBLIST、410 库预链接、只读挂载可重挂性和实际服务健康尚待上板普查确认；任何硬性放行失败均停止测量。

### 关 PIE 第二阶段恢复重挂与只读根安全门（2026-11-05）

计划与进度：仅修订 `docs/nopie_experiment_plan.md`、`memdiff/scripts/nopie_stage2_load_bias.sh`，本机离线检查，无开发板访问或真实 remount。第二阶段前置条件新增用户确认开发板可重新刷机恢复，并记录恢复镜像完整版本；未确认则不执行。方案已列出 `/etc` 写入被阻断时的三种候选：现有内核命令行到 manager 环境的通路、已有可写配置分区、重新出带 drop-in 的实验镜像，均只列可行性与单变量影响，不实施。

脚本已闭合：`mount-check` 记录 `/`、`/etc`、目标父目录的设备、文件系统类型、挂载选项与 boot ID；目标为 device-mapper、squashfs/erofs/其它只读类型、cmdline 或可用的 dmsetup table 含 verity、overlay 下层只读或不能核实时，`state/<scope>/safety_mount_check_<boot-id>.tsv` 记阻断并返回“第二阶段不可在此镜像以写 /etc 方式进行”。每次 `remount-rw` 前重跑相同安全检查。`restore` 与 `verify-restored` 在各自当前开机若目标不可写，重新过安全门并临时重挂；文件恢复/核对后立即恢复原挂载选项。每次动作的 boot ID、前后选项写 `state/<scope>/mount_events.tsv`，失败时尝试紧急恢复并保留证据。模拟测试五类挂载条件（普通 ext4 通过；dm、squashfs、verity、overlay 下层只读拦截），以及跨两个模拟 boot ID 的恢复和最终核对各自重挂/恢复，均符合预期；`bash -n` 与 `git diff --check` 通过。证据与执行说明见上述方案及脚本；未取得板上的实际安全检查结果。

挂账：开发板可重新刷机的确认、恢复镜像版本、实际挂载拓扑及两个 systemd drop-in 的安全门结果须在第二阶段前记录；任何阻断都不得尝试写 `/etc` 或绕到 `/run`。本轮未验证实际镜像是否允许 remount，亦未进行加载偏置测量。


### TPMS 内存类用例只读静态审查（2026-11-05）

已完成：`docs/tpms_memory_test_audit.md`，逐条列出采集时机/次数、数据库去重、指标与 swap 口径、进程集合、有效性检查，以及按可信度影响排序的八项建议；每项附当前源码路径/行号及已有证据。仅本地静态读取与历史 SQLite 只读查询，未使用开发板、未改 TPMS 源码，建议均未实施。

已闭合：wait_for_stability 仅日志、无判据/阈值/上限；300 秒从调用重启前主机时间起算，后两项通常复用主内存快照。历史 GCC/LLVM3 采集脚本起止 uptime 分别 297.44–307.67 / 330.52–341.23 秒，不能称固定开机 300 秒；已有 memcheck 仅内存最早达标为 628–1080 秒，但不是同次 TPMS 开机。App main/create 首条保留已用历史 XML/DB 复核；内存同受唯一键约束，当前检查点 110 条内存记录无重复，不误称默认重复内存已被吞。MEMINFO_ProcessPSS 不加 SwapPss，既有配对 −138/+297 kB 支持 memps PSS 为 resident；MEMPS 另加 3D/GEM(PSS)。Idle 取 Used (Mem+Swap)，但原输出与 Used (Mem) 相等且工具内部源码缺失，不能确认其实际 swap 公式。双镜像详情/Excel 已保留并集与 N/A，缺身份核验及单边贡献分解；函数 True 不保证解析/数据有效。

限制与挂账：未找到 perf-rigor v12 设计文档，所有覆盖分类与章节均无法核验，不将“文档缺失”冒充“设计未覆盖”。现有单快照流程不足以单独确认 10–20 MB 为稳定可重复的镜像差异。新增建议均保持 legacy 默认，并独立标记新口径，避免改变 SR 总部既有结果的可比性。206 个源码/配置文件 SHA-256 核对不变；报告与本状态段同一 memdiff 本地提交，作者 Hao Lin <hao.lin@samsung.com>，不 push；已有其他未提交修改保留。


### TPMS 内存严谨模式实现与离线验证（2026-11-05）

开工：读取状态及 `docs/tpms_memory_test_audit.md`，9 个核心文件 SHA-256 与审查时全部一致；保存初始状态/哈希后，从 memdiff 新建 `tpms-memory-rigor`。含其它分支和未跟踪文件的 perf-rigor/v12 检索未找到设计或实现，无可接入的重叠接口。现有 WEAK/LTO 段、两篇无关报告修改及其它未跟踪材料保留；本任务只暂存新增状态段。

实现完成：集中 `memory_rigor` 配置默认关闭，仅 TV profile 开启 B=3、N=5；每次重启后用板上 uptime/boot_id 门控（至少600秒、30秒/10样本、内存两极差<1%、CPU均值≤21%、最长1800秒），上限采集显式标记。新增每命令 rc/stdout/stderr/起止时间、顺序整组快照、smaps_rollup 与完整进程身份、zram/swap 细项、覆盖率与失败传播；ION 默认关闭，可选时在全部 base 后独立采集。旧名称仅取首 boot/首 base 样本且须有效；其它 profile/旧唯一索引/10%阈值不改。

存储/报告：独立 run/gate/sample/process/aggregate 表保留全部样本，无效值存 NULL，不入聚合；按 boot 中位数与跨 boot 均值/极差比较，双方完整有效且均值差绝对值超过两侧极差才标“差异超出波动”。新增共同/单边进程及显式系统会计残差分解，缺失不补零；保存 memps NEVRA/SHA/实际来源，禁止未标记的 latest 回退。页面附加严谨区域及离线 JSON 报告；旧 Excel 格式保持。

离线验证：84/84 项通过（新增81、原有3），单 CPU、nice19、idle I/O、Python上限768MiB；最终入口耗时7.61秒、峰值RSS53912kB。两镜像×三个旧解析器报表字节不变；关闭分支后的旧主机函数AST、目标脚本主体、其它profile哈希及旧比较JSON不变。GCC/LLVM3旧Idle均488MB、ProcessPSS=416969/423552kB匹配历史DB；raw smaps总量572599/554891/557390/548902kB匹配原映射分析，rollup各自匹配其totals，二者不混用。LLVM gate重放899/869秒与nopie_policy_rehearsal.tsv一致；历史材料缺新身份/命令证据，不能冒充完整3×5严谨样本，正式比较按无效/不足拒绝结论。

报告/限制：`docs/tpms_memory_rigor_changes.md` 按审查建议1–8说明实现、兼容性、全部命令/结果、已知限制及仅列出的上板冒烟步骤；证据在 `docs/evidence/memory_rigor/`。默认内存门控+间隔最坏预算96分钟，若15次采集命令均用满300秒则171分钟加传输/重启等；按历史时序约LLVM50分钟、GCC99分钟加采集传输，完整套件初始gate还可能增加30分钟。未使用开发板、未联网、未部署、未实测耗时；覆盖率、UEP/目录拉取及目标工具兼容性须用户开板后冒烟确认。代码与本段同一分支本地提交，作者Hao Lin <hao.lin@samsung.com>，不push。


### TPMS 当前运行目录内存严谨模式修正（2026-11-05）

已确认常规运行目录 `/home/linhao/lss/memory_check/TPMS`，当前 tpms-memory-rigor 原已检出73fee4b8e，直接修改此工作树，无需用户切换/合并。根TPMS.sh及历史日志路径作为证据；历史专项memdiff/runtime脚本副本不改。修改前备份 `/home/linhao/lss/memory_check/tpms_backup_20261105_182012.tar.gz`，SHA-256 `62f56c1b64dce3c445371bc1105be0d046cbc67a41311987f76abe5d13d0cd62`；清单、排除项、git状态与恢复步骤在同名_metadata目录。

修正：PF_KTHREAD flags/ppid与退出进程分类；排除采集者子孙；fixed_uptime默认1800秒及gate策略、首次满足时刻与中文警告；单tar归档SHA校验/安全解包/耗时文件数/成功与失败finally清理核对；memps允许原流程latest回落并显式来源警告；rigor_v2方法标记、legacy_300s混用提示；UsedMem=MemTotal−MemAvailable拆分；每boot默认至少3有效样本；TV initial_gate开启、ION关闭。旧指标名/数值/10%规则与非TV关闭行为保留。

离线最终135项Python测试（原84+本轮51）和1项页面渲染全部通过，7项旧输出字节比对一致；历史DB、raw smaps/rollup各自参考、LLVM gate时刻一致，GCC无rehearsal TSV对应行明确N/A。测试单CPU串行、低优先级；完整日志/资源/备份信息在docs/evidence/memory_rigor_revision。fixed含initial约96–126分钟，gate历史情景LLVM约64/GCC约129分钟，均另加采集传输等；非上板实测。更新报告含boots=1/samples=2/min_valid=2冒烟与恢复步骤。本轮未用板、未联网，只本地提交；无关已有修改保留。


### 严谨内存模式真实板上冒烟（2026-11-06）

用户确认IP192.168.108.26、LLVM Tizen10.0 Kantesu2e；被测b45bce017，四项身份前后均通过，实际BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611030601。临时profile只开启三个内存用例，boots=1/samples=2/min_valid=2/initial_gate=false/fixed_uptime=600/ION=false；未修改正式配置与生产代码。

总体不通过：11项前置/恢复/失败展示检查通过，3个实际内存用例均False。root实际UID0，但executeCmd_result stdout保留TPMS_RC标记，prepare将其整体与字符串0比较而误报memory capture requires root；在push/安装/重启/采集前退出。实际0次重启、0份probe/snapshot，内核线程、覆盖率、扰动和采集传输耗时均N/A，不假装通过。失败run入独立DB1行，样本/聚合/旧指标0行；原页面函数可渲染0/2失败信息。

恢复完成：tar -C自检与临时bin目录已删，memory_rigor目录测前测后不存在，原结果文件SHA、挂载、governor、memps NEVRA/SHA相同；memps已预装、未调用安装器，URL未知且无latest回落。root由5001临时切到0，结束恢复root off/UID5001；boot_id未变。报告docs/tpms_memory_rigor_smoke.md，原始证据memdiff/data/memory_rigor_smoke/20261106_134725/。离线135 Python+1 UI仍全部通过，说明原模拟未覆盖真实尾标记契约。修复后正式完整入口静态等待/间隔预算约126分钟+15份采集传输及其它开销，本轮不能实测校准。不修代码、不push；报告/状态/原始证据本地提交并重新导出审查包。


### 严谨内存模式 root 输出契约修复（2026-11-06）

基于defd19c0d，仅修executeCmd_result：stdout移除当前UUID尾标记及printf分隔换行、CRLF归一化；raw_stdout保留原始证据。退出码/超时、旧接口和严格UID==0判断不变。runner各调用点核对见docs/tpms_memory_rigor_stdout_fix.md。

新增12项真实sdb格式回归测试，147 Python+1 UI全部通过，历史回放一致，7例旧输出字节比对一致；所有Python/测试均CPU0/nice19串行。证据memdiff/data/memory_rigor_smoke/20261106_141943/。本阶段未连接开发板，等待用户再次确认已开板、IP192.168.108.26、LLVM Tizen10.0 KantSU2E后重跑同参数冒烟。


### root修复后同板重跑完成（2026-11-06）

离线147 Python+1 UI及7例旧模式逐字节比对全通过后，用户再次确认开板、192.168.108.26、LLVM Tizen10.0 KantSU2E不变。被测c38cb45ee，同参数1次重启×2样本、fixed600、initial_gate=false、ION=false；三个内存用例均True，2/2有效。真板stdout=0\n、raw_stdout含CRLF/TPMS_RC，严格root误判已修复；SHA和归档回执通过。

样本uptime602.47/654.99秒；各211内核线程，覆盖率114/114与111/111=100%，3个首次stat ENOENT退出、无权限失败。板上采集20.41/19.48秒、打包均0.33秒、拉取1.105/1.007秒；端到端至清理26.135/25.072秒。DB runs/gates/samples/processes/aggregates/legacy行数1/1/44/650/110/120；原页面真实DB渲染通过。600.73秒到点时内存不稳、CPU27.808%，页面保留警告；采集窗口CPU约42%、MemAvailable下降9424/5852kB，不能声称无扰动或已证明10–20MB比较可信。正式3×5/fixed1800含initial_gate预算102.40–132.40分钟加其它开销，初始等待用满约2小时12分24秒。

恢复root off/UID5001；临时profile/上传脚本/run目录/归档清理，memory_rigor父目录恢复不存在，原结果、配置、源码、governor、memps不变，未安装rpm。原恢复日志因/proc/mounts顺序不同报失败，离线核对38条完整挂载记录集合一致；保留原失败日志和独立复核，不改挂载。报告docs/tpms_memory_rigor_smoke.md；完整证据memdiff/data/memory_rigor_smoke/20261106_141943/。代码/报告/证据本地提交，作者Hao Lin <hao.lin@samsung.com>，不push；审查包patch从defd19c0d到最终提交。

### VD LLVM 内存优化周报数据表（2026-11-10）

计划与进度：按周报要求离线核对第一轮、第二轮和第三轮的报告与原始分析 TSV；统一将 kB/KiB 除以 1024 换算 MiB，逐次列出 TPMS、用户态 PSS/PSS+SwapPss、15 程序组、410 库私脏、单侧进程、匿名/栈/页表和代码段。只整理证据，不访问开发板或网络，不修改采集脚本与分析代码。

闭合：`memdiff/reports/weekly_data_table.md` 已逐项给出采集日期、次数、指标口径、两次极差、文件路径及行号；保留第一轮/第三轮 LLVM、PSS/PSS+SwapPss、r--/rw-、全进程/严格配对的多值项。报告引用的 148 个带行号文件位置均存在且行号在文件范围内。主要原始表在 `memdiff/data/gcc_baseline/analysis/`、`memdiff/data/llvm_round3/analysis/`，TPMS 原始 `memps.txt` 位于各轮 `boot3/tpms/raw_export/`。

挂账：三轮完整镜像发布版本、历史 TPMS 524/531 MB 的原始 KiB/日期/次数、旧快照准确线程数与每线程平均栈 PSS 未在现有证据中找到；报告明确写“未找到”，不估算。分卷和实验方案未变。本次只本地提交周报表与本节状态，不 push。

### 预链接 bind mount 可行性只读探查（2026-11-11）

计划：先经 SDB 读取板子四项身份、`/etc/os-release` 和 BUILD_ID；身份通过后只读核对挂载、预链接工具、四个服务及加载器诊断，并在 `/opt/usr` 内用小文件做一次可恢复的 bind mount 自检。不重启、不安装、不做持久修改。

进度与停止条件：`sdb devices` 为空，`sdb connect 192.168.108.26` 返回 1（`failed to connect`）；ping 和 TCP 26101 可达，但 SDB 会话不可用。`sdb -s ... shell` 身份命令均返回 `target not found`。故 LLVM 镜像身份未确认，按门禁停止；板上挂载、自检、服务检查、`LD_DEBUG` 均未执行，也未调用 `sdb root on`。证据 `memdiff/data/prelink_bind_probe/host_connection.json`、`identity_commands.json`；报告 `memdiff/reports/prelink_bind_probe.md`。

挂账：待 SDB 恢复后先核对身份，再完整执行本任务。当前无法确认板上 UID，不能把“未开启 root”写成“已核实 root off”。

### 预链接 bind mount 可行性探查完成（2026-11-11）

进度：此前 SDB 连接失败的记录保留；用户确认连接后重新接入同一 IP，`identity_valid/checks.json` 四项均通过。当前 `BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`，开机 ID `0d30d3eb-a65b-44e2-b1d6-ee93e2c39af5`。开发机侧所有采集均 CPU0/nice19 串行，板上未重启、安装、改系统目录文件或重启服务。证据 `memdiff/data/prelink_bind_probe/identity_valid/` 与 `board/`。

闭合：`/opt/usr` 内源文件到空目标文件的 bind mount 自检读回内容一致，随后立即 umount 并清理，独立核对源、目标和挂载均无残留；第一次因板上无 `cmp` 误报的原文也保留。`command -v prelink` 与 RPM 查询远端返回码均为 1；虽有 `/etc/prelink.conf`，板上无可调用 prelink。四进程 AT_SECURE 为 tvs-daemon=0、tv-viewer=0、launchpad-loader=1、TIFSDaemon=0；去重 `.so` 路径数依次 297/336/273/304。`LD_DEBUG=libs /bin/true` 输出 `[vdprelink failed]`，无 `prelink checking` 行。报告 `memdiff/reports/prelink_bind_probe.md`；可复算 `process_summary.json`、`library_private_dirty.tsv`。

恢复与挂账：两次临时 root 均已 `sdb root off`、UID 回到 5001；boot_id 未变，`/opt/usr/tmp_probe` 不存在。tvs-daemon 和 TIFSDaemon 有 systemd 依赖，tv-viewer 和 launchpad-loader 没有独立 unit；本轮不认定任何一个可安全单独重启。只证实临时文件 bind 的能力，未验证替换系统库后的加载器行为或收益。`find / -xdev` 的 `/zone/template/securedata` 权限错误留作搜索范围限制。证据详见同一报告和 `board/final_state.stdout`。

### 预链接验证准备：overlay 审计与进程拆分（2026-11-11）

计划与进度：先向用户确认板子 IP=192.168.108.26，再核对 armv7l、NT72671D、KSU2E、clang 内核及 `BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`，全部通过。板上只读采集 `/proc/mounts`、三个 upperdir 的 `find -xdev` 列表、与 `/.org_rootfs` 的文件大小/SHA256 对比、三个进程的 maps 库闭包和 480 个库的 SHA256/RPM/ELF 类型；本机只用保存的 GCC/LLVM3 各两次 `02_steady/smaps_raw.txt.gz` 做六类 Private_Dirty 拆分。报告 `memdiff/reports/prelink_overlay_prep.md`，原始输出及复算脚本/TSV 在 `memdiff/data/prelink_overlay_prep/`；开发机 CPU0/nice19 串行，脚本不读终端输入。

已闭合：可读 upperdir 共 107 条目（platform 105、factory_peq/prd 各 1），常规文件 55 个，对 lower 为 6 个相同、2 个不同、47 个新增；14 个字符设备 0/0 为 `/etc/emanual_icon/` 删除标记。指定系统目录 `/usr/lib`、`/usr/bin`、`/lib`、`/prd/usr/lib` 中 upperdir ELF 覆盖 **0 个**，39 个 `/usr/bin/target_view/.../__pycache__` 文件均非 ELF。三个进程 a+b+c+d 文件映射私脏的 LLVM−GCC 均值差为 tvs-daemon +1862 KiB、tv-viewer +1424 KiB、TIFSDaemon +1176 KiB；这是候选量，不是实测可回收收益。当前 LLVM 映射库并集 480 个，其中 6 个不在 `/etc/prelink.conf` 的目录。证据 `board_summary.json`、`upper_inventory.tsv`、`upper_file_comparisons.tsv`、`upper_whiteouts.tsv`、`upper_elf_magic.tsv`、`components_summary.tsv`、`library_union.tsv`。

恢复与挂账：没有板上文件写入或重启；临时 `sdb root on` 后已 `root off`，最终 UID=5001、boot_id 未变（`board/final_state.stdout`）。`/opt/.overlay/platform/upperdir/zone/securezone` 即使 root 也 Permission denied，不能声称该子树全量清点；不影响指定系统 ELF 路径。upperdir 的早期 mtime 和 `/root/.bash_history`、target_view `.pyc` 可提示运行期/历史文件，但不足以证明跨刷机保留或手工安装。`/usr/lib/libc-2.40.so` 的 `rpm -qf` 未归属，符号链接 `/usr/lib/libc.so.6` 归属 glibc-2.40-1.72；清单保留原路径未归属。下一步需要用户和 Claude 设计实验镜像验证实际预链接收益，本轮不做。结果只上传用户指定的 `lhmax2010/memory-check`，不推送本机 TPMS 分支或其他仓库。

### tvs-daemon / tv-viewer 代码映射拆分（2026-11-11）

计划与进度：仅用 GCC 与 LLVM 第三轮各两次 `02_steady/smaps_raw.txt.gz`，沿用 `data/prelink_overlay_prep/components_per_boot.tsv` 的进程配对和 `other` 分类，逐 r-x ELF 对象复算六项 smaps 指标及完整快照映射进程数；使用同一交叉 readelf 检查前十对象的两侧板上 ELF。开发机 CPU0、nice19、ionice3 串行，Python 4 GB 虚拟内存上限；不上板，分析阶段不联网。报告 `memdiff/reports/tvs_daemon_code_pages.md`，逐次表、均值表、分类表、ELF 原始输出和脚本在 `memdiff/data/tvs_daemon_code_pages/`。

已闭合：tvs-daemon 的 `other` Pss 差 +5768.5 KiB 全部为主程序或 `.so` 的 r-x 映射差；前五对象 `libtvs-api-native`、`libtvs-dvb-si`、`libtvs-iss`、`libtvs-util`、`libtvs-dsm` 分别 +452、+372、+352、+344、+324 KiB，Rss 同量增加、映射进程数不变。按报告列明的 Rss/进程数观察规则，(a) +5446.0 KiB，(b) +351.5 KiB，另有正差 +99.0 KiB 未确定、负向抵消 -128.0 KiB。GCC 前十对象的板上副本均无 `.symtab`，LTO 痕迹规则下无法判定是否做过 LTO；不能把差额归因于 LTO。tv-viewer 的 `other` 差 +963.5 KiB，其中 r-x 对象 +856.0 KiB、非目标残差 +107.5 KiB。证据 `object_summary.tsv`、`other_coverage.tsv`、`object_classification.tsv`、`top10_elf.tsv`。

挂账：Rss 及映射进程数只能区分观察模式，无法逐页证明代码触发路径或共享因果；若需确认 LTO，须取得未 strip 的对应 GCC 构建产物或构建日志。此次只将新报告、数据与本节状态上传到 `lhmax2010/memory-check`，不推送本机 TPMS 分支的其他内容。

### 当前 LLVM 代码驻留页 ELF 节归属（2026-11-11）

计划与进度：用户确认 IP `192.168.108.26` 后，先核对 armv7l、NT72671D、KSU2E、clang 内核及 `BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`；全部通过。只读采 tvs-daemon 与 tv-viewer 的 maps、前后 smaps、13 个对象的 39 个文件 VMA 的完整 pagemap（每 VMA 一次 dd+od），并原样拉回 13 个 ELF。任务文字称 12 个对象，但清单实际 13 个，按清单全部处理。板上未写文件、未重启；root off 后 UID 恢复 5001。原始命令与返回码 `memdiff/data/code_page_sections/collection.json`、`raw/`，板上与主机 ELF SHA256 逐一相同。开发机命令 CPU0/nice19 串行。

已闭合：交叉 readelf `-SW/-lW` 加文件偏移逐页交集，跨节页按字节分摊；39 个 VMA 的 pagemap present×页大小与 smaps Rss 全部相同。13 对象当前 r-x 驻留 8820.0 KiB，其中加载器相关节 5041.7 KiB（57.2%）、`.text` 2744.9 KiB（31.1%）。GCC 两次的同对象 r-x Rss 均值 4390.0 KiB；由 GCC 每对象加载器节静态大小与 Rss 上界可严格推出加载器节驻留净增长至少 2590.6 KiB（总 r-x 差 4430.0 KiB 的 58.5%），但精确增长无法确定。8 个对象的 GCC r-x Rss 小于其加载器相关节静态大小，证明这些表未整段驻留；12 个库与第三轮 LLVM ELF 逐字节相同，tv-viewer 主程序不同。报告 `memdiff/reports/code_page_sections.md`；逐节及逐对象数据在 `memdiff/data/code_page_sections/sections.tsv`、`section_residency.tsv`、`object_sections_wide.tsv`、`object_summary.tsv`。

挂账：历史 GCC 没有逐页 pagemap，故不能精确分解 ELF 节的 LLVM−GCC 差值；当前不同 BUILD_ID 与未锁定工作负载也限制跨镜像因果判断。恢复预链接能否省这部分 r-x 驻留仍未确定，需要用户和 Claude 另行设计同版镜像实验。只把本次报告、数据与状态上传到 `lhmax2010/memory-check`，不带本机仓库其他改动。

### 全系统代码映射 ELF 节归属与动态表复核（2026-11-11）

计划与进度：同一 IP `192.168.108.26` 先核对 armv7l、NT72671D、KSU2E、clang 内核及与上轮相同的 `BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`，全部通过。板上 root 只读采初始 322 个 PID：316 个完整，6 个退出/不完整不重试；每 PID 一次 SDB shell，在其内对每个 r-xp 文件 VMA 一次 dd+od 读取完整 pagemap。拉回 1555 个映射路径，1549 个 SHA256 两侧一致、6 个失败；其中可用 ELF 1452 个。root off 后 UID 和 boot ID 均恢复/不变。板上无文件写入、无重启、无部署。原始命令、返回码、输出与 SHA 在 `memdiff/data/system_code_page_sections/collection.json`、`raw/`、`elf/`；进度日志 `collect.log` 以“已结束 … 状态=DONE”结束。

已闭合：解析 16414 个 r-xp 文件 VMA，pagemap present×页大小与 smaps Rss 逐 VMA 完全相同；同文件偏移取并集，r-x 私脏、TEXTREL、inode 异常等单列排除，节归属仍用上轮按字节交集的算法。可信共同文件 1360 个，LLVM 唯一 r-x 驻留 191844.0 KiB，GCC 两次 Pss 和均值 174892.5 KiB，差 +16951.5 KiB；LLVM 加载器节驻留 62256.4 KiB，加载器节净增下界 +8902.4 KiB；去加载器后 ≤GCC 1102 个、>GCC 258 个。prelink.conf 8 个目录内子集 1072 个，差 +16973.0 KiB、加载器节 47686.0 KiB、下界 +10322.1 KiB、≤/> 为 831/241。周报“clang r-x +5.168457 MiB”是第三轮 1292 匹配路径的逐映射 Pss，而非本次唯一页；本次同路径同 Pss 口径相对历史 GCC 为 +9912.5 KiB，BUILD_ID 和运行集合不同，不解释为编译器效应。来源 `memdiff/reports/system_code_page_sections.md` 与 `summary.tsv`、`weekly_reconciliation.json`、`file_residency.tsv`。

离线核对：GCC 板上 ELF 副本 1463 个，带任一预链接标记 425 个；LLVM 当前 ELF 1452 个，带标记 0 个。`.rel.dyn` 为 REL/RELA 的 GCC 1300/163、LLVM 1452/0。共同 ELF 1365 个，其动态符号 WEAK 已定义合计 GCC 62857、LLVM 188193；13 个上轮对象逐项见 `thirteen_dynamic.tsv`。交叉 c++filt 首次缺 libbfd 失败的日志保留，改用同一 GBS root 的 `usr/lib64` 后仅重跑符号反解并成功；readelf 错误 0。`qa.json` 八项一致性检查全部通过。原始表、脚本和日志在 `memdiff/data/system_code_page_sections/`。

挂账：6 个采集时退出的 PID、6 个拉取失败路径、114 个共同文件因非 ELF/缺副本或无法可靠去重不进入 ELF 节汇总；完整清单在报告及数据表。GCC Pss 逐映射舍入且两侧镜像/进程集合不同，跨镜像差额不能直接归因于编译器。ELF 符号名可识别模板候选和类成员，但无法单凭 c++filt 证明类内定义或 inline，报告标“未确定”。只把本次结果推到用户指定的 `lhmax2010/memory-check`。


### 预链接实际覆盖的全系统 r-x Pss 复核（2026-11-12）

计划与进度：完全离线复用 `data/system_code_page_sections/` 的可信共同文件、当前 LLVM VMA/Pagemap 与 GCC 两次 `02_steady/smaps_raw.txt.gz`，并读取两侧 ELF 副本；不上板、不联网。开发机 CPU0/nice19 串行，Python 虚拟内存上限 2.5 GB，进度和结束状态落在 `memdiff/data/prelink_group_attribution/run.log`。逐文件表、分组表、主程序归属、SHA256 噪声底和 GNU_LIBLIST 清单均放在该数据目录，报告为 `memdiff/reports/prelink_group_attribution.md`。

已闭合：沿用 1360 个可信共同文件，LLVM r-x 逐映射 Pss 和 186077 KiB 对 GCC 两次均值 174892.5 KiB，差 +11184.5 KiB；LLVM 唯一驻留比其 Pss 和高 5767 KiB，不把全额断定为取整。GCC 的 GNU_LIBLIST 主程序共 10 个；当前可信集合出现 9 个，另一个 `acm-service` 未运行且没有本次 ELF 副本。甲/乙/丙/丁/戊分别 9/62/348/857/84 文件，Pss 差 +580/+5398/+417.5/+5072.5/-283.5 KiB；乙组 GCC 最大 r-x Rss 小于加载器节静态大小仅 22/62，与“多数成立”的预期不符。甲乙观测净增下界合计 +3397.6 KiB，按比例折算的 LLVM 加载器节 Pss 上界估计 8042.1 KiB；同字节 31 文件噪声底 Pss 差合计 -48 KiB，逐文件中位数 0、90 分位 4 KiB。证据 `memdiff/data/prelink_group_attribution/group_summary.tsv`、`rounding_by_mapper_count.tsv`、`per_file.tsv`、`summary.json` 和报告。

挂账：当前 `acm-service` 的 PIE 状态未能用本次 ELF 副本验证；其余 9 个均为 ET_DYN 且带 PIE。LLVM 进程主程序由保存 maps 的最低地址 r-x 文件映射推定，未有同次 `/proc/PID/exe` 核验；本次 LLVM 与历史 GCC 的 BUILD_ID、服务集合和时刻不同，观测下界/上界不是实际恢复预链接收益。本次只将报告、数据与状态的新增小节推到 `lhmax2010/memory-check`，保留 TPMS 工作区既有未提交改动，不推送原仓库其他内容。


### 交叉 prelink 工具与 GCC 副本逐字节验证（2026-11-12）

计划与进度：离线使用已拉回的 1463 个 GCC ELF 副本，不上板、不联 VD 网络；从公开 Yocto prelink-cross 源码取 2013 cross 分支、最新 cross 分支与当前 master。所有源码、构建根、工具二进制和试验根在仓库外 `/tmp/prelink-tool-validation-20261112/`；CPU0/nice19 串行，`make -C src -j1`，虚拟内存上限 2,500,000 KiB。版本/提交/SHA256/配置参数见 `memdiff/data/prelink_tool_validation/build_manifest.json`、`tool_versions.tsv`，配置和编译日志逐阶段保存。425 个带预链接标记 ELF 全部试验 `--verify` 和独立根上的 `-u`；进度、返回码、失败原文与 QA 在同一数据目录。报告为 `memdiff/reports/prelink_tool_validation.md`。

已闭合：2013 与最新 cross 工具均编出 x86_64 的 `prelink`、`prelink-rtld`；当前 master 无 `--root/--rtld`，VD 的 `--ignore-soname` 在上游版本中也不存在。原样 GCC 副本根验证：两版 cross 各逐字节一致 4、不一致 1、报错 420；master 报错 425。以 ELF 自身 SONAME 唯一对应关系补 681 个推定软链接的诊断根，两版 cross 分别一致/不一致/报错 4/286/135 与 4/288/133；前 20 个不一致的差异节已用单独诊断工具捕获在 `mismatch_sections_top20.tsv`，正式计数工具未修改。独立根中 425/425 个 ELF `-u` 成功，标记消失、readelf 可解析，逐文件大小在 `undo_results.tsv`。原样与诊断根的 1463 个 ELF 文件字节均与仓库副本相同。证据 `verify_summary.tsv`、`alias_verify_summary.tsv`、`root_integrity_summary.json`、`qa.json` 及报告。

TIFSDaemon：保存 ELF 的 NEEDED 闭包可追到 284 个路径，`libfkpInternal.so` 唯一副本为 `/opt/usr/apps/Ddrm/fkp/lib/libfkpInternal.so`，由 `libfkp.so.0.1.0` 引用；该目录不在原 `--ld-library-path` 或 8 行 prelink.conf。`libcamera-control.so` 的保存路径 `/hal/lib` 也在两者之外。19 个目标里 8 个没有本地 ELF 副本；有副本的 11 个目标中仅 TIFSDaemon 找到上述目录外库。证据 `dependency_edges.tsv`、`outside_ld_path.tsv`、`missing_copies.tsv`。补 FKP 目录、再补 HAL 目录及 prelink.conf 的五组隔离试验均未改动 TIFSDaemon，虽然命令返回 0，实际先报保存根缺 `libfactory-interface.so`，故不能判断补目录是否足够或是否需同时更新配置；证据 `tifs_interp_trials.tsv` 与对应原始日志。

挂账：只凭不完整的 GCC ELF 副本、推定链接和缺少 VD 私有 `--ignore-soname` 的上游工具，不能证明与 VD 出镜像工具逐字节一致；其余 8 个缺副本目标的依赖、TIFSDaemon 完整根下的预链接结果未确定。需要内网提供完整 GCC 根或缺失的实际文件及 VD prelink/vdprelink 对应源码/补丁，后续由用户和 Claude 决定；本轮未访问开发板。仅推送本轮报告、数据与状态新增小节到 `lhmax2010/memory-check`，不带 TPMS 工作区已有未提交改动。

### GCC PERF 板上预链接撤销 A/B：准备阶段停止（2026-11-12）

计划与进度：用户确认 IP `192.168.108.26`，并将 tvs-daemon 门禁更正为 `GNU_LIBLIST + .gnu.prelink_undo`。身份、BUILD_ID、板上/本机 SHA256、readelf 标记均通过；本轮板上 `BUILD_ID=T-KSU2EJAKUC-0101-PERF-202610010416`。八个 prelink.conf 目录只读筛出 421 行、去重 419 个带 `.gnu.prelink_undo` 字节串的候选文件，尚未逐 ELF 正式核对。证据 `memdiff/data/prelink_undo_ab/preflight.json`、`board_prelink_candidates.txt`，报告 `memdiff/reports/prelink_undo_ab.md`。

停止条件：板上缺 `getfattr/setfattr` 等通用扩展属性工具；从官方 Tizen Base 临时提取的工具在 `/opt/usr` 暂存目录执行时被拒绝（直接执行 126，经动态加载器 127）。无法满足“全部扩展属性可备份、可恢复才改写”的硬条件，故实际修改程序/库数均为 0，三个状态的开机和内存测量均未执行；没有收益数据。证据 `board_xattr_tools.stdout`、`attr_tool_probe.stdout`、`attr_tool_probe.stderr`。旧 GCC 副本的本机 `prelink -u` 成功不替代板上文件属性门禁。

恢复核对：仅曾推入两份临时属性工具，现已删除，暂存目录不存在；板上系统 ELF 未修改且 tvs-daemon SHA256 不变；未重启，boot ID 不变；`sdb root off` 后 UID 5001。证据 `board_cleanup.stdout`、`post_cleanup_identity.stdout`。挂账：需有板上实际可执行的完整 xattr 备份/恢复工具，或能逐文件证明并恢复全部原属性的等效方案，才可重新开展实验。

### GCC 板 UEP/overlay 三类文件探测（2026-11-12）

计划与进度：用户再次确认板子 IP `192.168.108.26`；armv7l、NT72671D、KSU2E、GCC 内核及 `BUILD_ID=T-KSU2EJAKUC-0101-PERF-202610010416` 均通过。仅在 `/root/uep_probe/` 暂存官方 attr RPM 的工具和一个 `/usr/bin/whoami` 原件备份；选用该工具的只读筛选、交叉 readelf `.comment` 偏移及原状态执行见 `memdiff/data/uep_overlay_probe/selected_candidate.json` 和 `raw/candidate_whoami_*`。脚本不读终端，开发机 CPU0/nice19 串行，进度与结束状态见 `progress.log`、`prepare_console.log`、`mutate_console.log`。

已闭合：`/root` 下未签名 getfattr 直接执行及经动态加载器执行均成功；`whoami` 原样覆盖并出现 overlay upper 副本后仍可执行；只把非加载的 `.comment` 首字节 `G→H` 后仍可执行。原样 copy-up 的 SHA256 与原件相同，单字节改动的 SHA256 与本机对照件相同。原件、原样副本、改单字节版和写回版的属主/权限、getcap、chsmack 与全部 getfattr 输出一致，仅有 `security.SMACK64=0x5f`；12 组 dmesg/dlog 前后快照未见新增签名/UEP/kUEP 匹配行。证据 `memdiff/reports/uep_overlay_probe.md`、`data/uep_overlay_probe/attr_probe.json`、`mutation_state.json`、`log_delta_summary.json` 及原始输出。

恢复核对：原字节已原地写回，SHA256 和属性恢复到基准，运行输出一致；`/root/uep_probe/` 已清理，未重启，boot ID 不变；`sdb root off` 后 UID 5001。按成功恢复分支，upper 中仍有与下层原件字节/已枚举属性一致的 `/usr/bin/whoami` 副本。挂账：本轮仅改非 ALLOC 的 `.comment`，不能推出撤销预链接后加载相关字节改动的 UEP 结果，也未验证 19 个目标程序/库或服务健康；不作内存收益结论。
