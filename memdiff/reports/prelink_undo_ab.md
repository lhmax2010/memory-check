# GCC PERF 镜像预链接撤销对照：准备阶段停止记录

采集日期：2026-11-12。板子：192.168.108.26。**三个状态的测量未启动**：在任何系统 ELF 改写或重启之前，元数据恢复门禁未通过。下文没有把未执行的实验写成收益。

## 身份与预链接门禁

`armv7l`、`NT72671D`、`dtsversion=...KSU2E` 和 GCC 编译的内核均通过。`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202610010416`，开机 ID `97c290b7-727f-4055-acbb-525ae5c7e134`。`/usr/bin/tvs-daemon` 板上和拉回副本的 SHA256 都是 `6e4c83d344dcb256c73d1b72a88c7273f179311d1ca0b85548a027345b20954e`，与 11 月 2 日 GCC 基线副本相同；交叉 readelf 确认它有 `GNU_LIBLIST` 和 `.gnu.prelink_undo`，没有 `GNU_PRELINKED`。按用户本轮更正，以前两者作为门禁，结果通过。证据：[`preflight.json`](../data/prelink_undo_ab/preflight.json)、[`board_preflight/`](../data/prelink_undo_ab/board_preflight/)。

八个 `prelink.conf` 目录中，`grep -alF .gnu.prelink_undo` 发现 421 行、去重 419 个候选文件，包含固定排除的 `/usr/lib/ld-linux.so.3`。目录有包含关系，且这是字节串筛选，**不是逐文件 readelf 确认后的带标记文件数**。板上没有 readelf；没有进行完整 ELF 拉回和核对。证据：[`board_prelink_candidates.txt`](../data/prelink_undo_ab/board_prelink_candidates.txt)、[`board_capability.stdout`](../data/prelink_undo_ab/board_capability.stdout)。

板上 `/opt/usr` 和 overlay 上层目录同在 VDFS `/dev/mmcblk0p21`，准备时可用 2,970,612 KiB。由于未确定最终待改文件集合及总大小，没有把空间门禁判为通过。证据：[`board_capability.stdout`](../data/prelink_undo_ab/board_capability.stdout)。

## 元数据恢复门禁与停止原因

板上没有 `getfattr`、`setfattr` 或可用的 Python/BusyBox；只有 `getcap`、`setcap` 和 `chsmack`，无法枚举并恢复**全部**扩展属性。为验证工具可用性，从官方 Tizen Base 快照的 `attr-2.5.1-1.87.armv7l.rpm` 临时提取 `getfattr`/`setfattr`，仅推到 `/opt/usr/tmp_prelink_undo_ab_20261112/`。RPM URL：`https://download.tizen.org/snapshots/TIZEN/Tizen/Tizen-Base/tizen-base_20261026.005418/repos/standard/packages/armv7l/attr-2.5.1-1.87.armv7l.rpm`，本机 RPM SHA256 `7306274c21c5b8b5bf412daf0a51c182359b46875b7d9ca5167308f104385335`。即使调整临时文件的 SMACK 标签，直接执行仍返回 `Operation not permitted`（126）；经 `/lib/ld-linux.so.3` 加载则报 `failed to map segment from shared object`（127）。这些是原始错误，不据此断言具体拒绝机制。证据：[`board_xattr_tools.stdout`](../data/prelink_undo_ab/board_xattr_tools.stdout)、[`attr_tool_probe.stdout`](../data/prelink_undo_ab/attr_tool_probe.stdout)、[`attr_tool_probe.stderr`](../data/prelink_undo_ab/attr_tool_probe.stderr)。

用户要求无法记录或恢复原属性的文件一律排除。因此目前**没有文件达到可改写门禁**，实际修改的程序数和库数均为 **0**；排除范围是所有待改文件，原因是无法完整备份并恢复扩展属性。固定排除项 `boot-helper-dyboost-tv` 和 `/usr/lib/ld-linux.so.3` 仍保留，未走到逐文件正式清单。没有执行 `prelink -u` 的上板替换、冷启动、健康检查、预链接诊断、memcheck 或 pagemap 测量；三个状态的差值和波动、与 LLVM 差值的对照均为**未测得**，不作估算。

## 清理和板子状态

临时提取的两个工具和探针文件已经删除，暂存目录不存在。未改写任何系统 ELF，`tvs-daemon` 的结束 SHA256 仍为 `6e4c83d344dcb256c73d1b72a88c7273f179311d1ca0b85548a027345b20954e`。未重启，结束开机 ID 与开始一致。`sdb root off` 后 UID 为 5001。证据：[`board_cleanup.stdout`](../data/prelink_undo_ab/board_cleanup.stdout)、[`post_cleanup_identity.stdout`](../data/prelink_undo_ab/post_cleanup_identity.stdout)。

## 挂账

若重开实验，需先提供板上可执行、可完整枚举和恢复扩展属性的工具及验证方法，或明确逐文件无需该工具也能验证所有原属性的依据；然后从完整文件清单、原件备份、权限与 xattr 快照、撤销版校验和两处空间检查重新开始。此前上游 `prelink -u` 的本机 425/425 通过结果只证明**旧副本可撤销**，不替代本次板上恢复门禁；见 [`prelink_tool_validation.md`](prelink_tool_validation.md)。
