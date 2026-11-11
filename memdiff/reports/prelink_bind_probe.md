# KantSU2E LLVM 板预链接 bind mount 可行性探查

采集日期：2026-11-11（Asia/Shanghai）；开发板：`192.168.108.26`。本次只读采集与两次 `/opt/usr` 内小文件 bind mount 自检，没有重启、安装、改系统文件或重启服务。开发机采集脚本为 `memdiff/data/prelink_bind_probe/collect_board.py`，只读解析脚本为同目录 `analyze.py`；每条 SDB 命令的参数、执行时间、返回码和 stdout/stderr 均保存于 `memdiff/data/prelink_bind_probe/board/`。**SDB 程序返回码与板上 shell 命令返回码可能不同**；prelink 两项另外在输出中记录了远端退出码。

## 1. 身份与过程

首次连接失败时按身份门禁停止，见 `memdiff/data/prelink_bind_probe/host_connection.json`、`identity_commands.json`。用户确认连接恢复后重新采集并通过四项核对：`armv7l`、设备型号含 `NT72671D`、cmdline 的 dtsversion 含 `KSU2E`、`/proc/version` 含 `clang version 22.1.8`。逐项原文及返回码：`memdiff/data/prelink_bind_probe/identity_valid/`，检查结果 `checks.json`。这确认了**当前板上为 LLVM 内核镜像**；不据此推断它与第三轮 2026-11-03 镜像的二进制完全相同。

- `/etc/os-release`：Tizen 10.0.0 (Tizen10/TV)，`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`；来源 `identity_valid/os_release.json`。
- `uname -a`：`Linux localhost 6.12.60 #1 SMP PREEMPT Fri Nov  6 04:17:15 UTC 2026 armv7l GNU/Linux`；来源 `identity_valid/uname_a.json`。
- 初始 uptime：`1847.14 5751.04` 秒字段（第二个为累计空闲时间）；来源 `identity_valid/uptime.json`。
- boot_id：`0d30d3eb-a65b-44e2-b1d6-ee93e2c39af5`；采集前后相同，来源 `identity_valid/boot_id.json`、`board/boot_id_restored.stdout`。
- 采集前 UID=5001；为读取 `/proc` 和挂载自检临时切 root（UID=0），两轮自检后均调用 `sdb root off`，最终 UID=5001；`/opt/usr/tmp_probe` 不存在。证据 `board/sdb_root_on.json`、`sdb_root_off.json`、`uid_restored_0.stdout`、`sdb_root_on_bind_retry.json`、`sdb_root_off_bind_retry.json`、`uid_restored_bind_retry_0.stdout`、`final_state.stdout`。

## 2. 文件系统与 bind 自检

根据 `memdiff/data/prelink_bind_probe/board/mountinfo.stdout` 对每个路径取最长匹配挂载点；选项同时列 mount 与 superblock：

| 查询路径 | 实际挂载点 | 类型 | 挂载选项 | superblock 选项 |
| --- | --- | --- | --- | --- |
| `/` | `/` | `overlay` | `rw,relatime` | `rw,lowerdir=/,upperdir=/opt/.overlay/platform/upperdir,workdir=/opt/.overlay/platform/workdir` |
| `/usr` | `/` | `overlay` | `rw,relatime` | `rw,lowerdir=/,upperdir=/opt/.overlay/platform/upperdir,workdir=/opt/.overlay/platform/workdir` |
| `/usr/lib` | `/` | `overlay` | `rw,relatime` | `rw,lowerdir=/,upperdir=/opt/.overlay/platform/upperdir,workdir=/opt/.overlay/platform/workdir` |
| `/usr/bin` | `/` | `overlay` | `rw,relatime` | `rw,lowerdir=/,upperdir=/opt/.overlay/platform/upperdir,workdir=/opt/.overlay/platform/workdir` |
| `/opt/usr` | `/opt` | `vdfs` | `rw,noatime` | `rw,dncs` |

`df -k /opt/usr` 显示 `/dev/mmcblk0p21`：容量 3,986,176 KiB、已用 1,034,336 KiB、可用 **2,951,840 KiB**（约 2,882.66 MiB），挂载于 `/opt`；来源 `board/df_opt_usr.stdout`。板上 `stat -f` 对 overlay/vdfs 显示 UNKNOWN，故类型以上述 mountinfo 为准。

第一次自检完成挂载、从目标读回标记和卸载清理，但板上没有 `cmp`，导致额外比对误报 `content_mismatch`；原文保留在 `board/bind_selftest_first.stdout`，随后 `bind_cleanup_verify_first.json` 返回 0。第二次改用 shell 内建 `read`，结果如下（`board/bind_selftest.stdout`）：

```text
tmp_probe_preexisting=0
target_initially_empty=1
bind_mount=ok
prelink-bind-source:20261111_090148
content_matches=1
cleanup_umount=ok
cleanup_files=ok
```

本次源文件位于 `/opt/usr/tmp_probe/`，目标为空文件且同在 `/opt/usr`，没有绑定任何系统目录文件。`board/bind_cleanup_verify.json` 返回 0，确认源/目标文件均不存在且目标不在 mountinfo；`board/final_state.stdout` 确认新建目录也已删除。**结论：板上有权限做这种同一可写分区内的临时文件 bind mount。**这并不验证把预链接库绑定到 `/usr/lib` 后的加载器效果或系统安全性。

## 3. 预链接工具

`command -v prelink` 与 `rpm -qa | grep -i prelink` 均无匹配，远端退出码均为 **1**（`board/prelink_command_rc.stdout`、`prelink_rpm_rc.stdout`）。因此板上**没有可调用的 prelink 命令，也没有名字匹配 prelink 的已装 RPM**；`prelink --version` 和 `--help` 中的 `--root` 行不适用。

`/etc/prelink.conf` 存在，`/etc/prelink.conf.d` 不存在；配置原文在 `board/prelink_conf_content.stdout`。按要求执行 `find / -xdev`，stdout 仅找到 `/etc/prelink.conf`，但 `/zone/template/securedata` 报 Permission denied；该遍历范围并非完全无遗漏。证据 `board/prelink_config.*`、`find_prelink.*`。此结果提示若要做预链接库 bind 实验，需另行取得已处理的库文件；本任务没有安装工具或处理库。

## 4. 四个进程

从 `pidof` 获取 PID、`/proc/PID/exe` 和 cgroup；ELF 类型为文件头 `e_type`（值 3=ET_DYN）。AT_SECURE 从 32 位 `/proc/PID/auxv` 的键 23 读取。`.so` 个数为 `/proc/PID/maps` 中**去重的文件路径数**，不是 VMA 数；私脏是这些 `.so` 文件的 `r--`/`rw-` VMA 在 `/proc/PID/smaps` 的 Private_Dirty 合计，单位 KiB。原始 maps/smaps/auxv、rpm、权限逐进程保存在 `board/proc_<name>_<PID>_*`；可复算表为 `process_summary.json`、`library_private_dirty.tsv`，每进程完整库清单为 `libraries_<name>.txt`。

| 进程 | PID | exe | ELF | RPM | cgroup unit | 模式 / 特权位 | getcap | AT_SECURE | .so 去重数 | .so r-- / rw- 私脏 KiB |
| --- | ---: | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| tvs-daemon | 691 | `/usr/bin/tvs-daemon` | ET_DYN | `tvs-main-loop-0.1.2-1.armv7l` | aaa_tvs_deamon.service | 755，setuid=0、setgid=0 | 无输出 | 0 | 297 | 2068 / 1128 |
| tv-viewer | 548 | `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | ET_DYN | `org.tizen.tv-viewer-0.3.8-1.armv7l` | 无独立 unit（init.scope） | 755，setuid=0、setgid=0 | 无输出 | 0 | 336 | 2388 / 80 |
| launchpad-loader | 754 | `/usr/bin/launchpad-loader` | ET_DYN | `launchpad-loader-0.49.30-1.armv7l` | 无独立 unit（init.scope） | 755，setuid=0、setgid=0 | /usr/bin/launchpad-loader cap_setgid,cap_sys_admin,cap_sys_nice,cap_mac_admin=ei | 1 | 273 | 2096 / 24 |
| TIFSDaemon | 979 | `/usr/bin/TIFSDaemon` | ET_DYN | `factory-service-9.0.01-0.armv7l` | org.tizen.tv.factory-service.service | 755，setuid=0、setgid=0 | 无输出 | 0 | 304 | 1952 / 36 |

`launchpad-loader` 的文件能力为 `cap_setgid,cap_sys_admin,cap_sys_nice,cap_mac_admin=ei`，与其 AT_SECURE=1 并列记录；不能仅凭此表证明能力是 AT_SECURE 唯一成因。四个文件均无 setuid/setgid 位。

### unit 属性与单独重启判断

**tvs-daemon** 的 unit 属性原文（`memdiff/data/prelink_bind_probe/board/proc_tvs-daemon_691_unit_show.stdout`）：

```text
Id=aaa_tvs_deamon.service
Type=forking
Restart=on-failure
User=
Group=
SmackProcessLabel=
CapabilityBoundingSet=cap_chown cap_dac_override cap_dac_read_search cap_fowner cap_fsetid cap_kill cap_setgid cap_setuid cap_setpcap cap_linux_immutable cap_net_bind_service cap_net_broadcast cap_net_admin cap_net_raw cap_ipc_lock cap_ipc_owner cap_sys_module cap_sys_rawio cap_sys_chroot cap_sys_ptrace cap_sys_pacct cap_sys_admin cap_sys_boot cap_sys_nice cap_sys_resource cap_sys_time cap_sys_tty_config cap_mknod cap_lease cap_audit_write cap_audit_control cap_setfcap cap_mac_override cap_mac_admin cap_syslog cap_wake_alarm cap_block_suspend cap_audit_read 0x26 0x27 0x28
TriggeredBy=
Requires=system.slice
After=system.slice
```
**tv-viewer**：`/proc/548/cgroup` 为 `init.scope`，`systemctl status 548` 返回“PID ... does not belong to any loaded unit”；所以 Type、Restart、User、Group、SmackProcessLabel、CapabilityBoundingSet **无独立 unit 可读**。原文：`memdiff/data/prelink_bind_probe/board/proc_tv-viewer_548_cgroup.stdout`、`proc_tv-viewer_548_systemctl_status_pid.stdout`。
**launchpad-loader**：`/proc/754/cgroup` 为 `init.scope`，`systemctl status 754` 返回“PID ... does not belong to any loaded unit”；所以 Type、Restart、User、Group、SmackProcessLabel、CapabilityBoundingSet **无独立 unit 可读**。原文：`memdiff/data/prelink_bind_probe/board/proc_launchpad-loader_754_cgroup.stdout`、`proc_launchpad-loader_754_systemctl_status_pid.stdout`。
**TIFSDaemon** 的 unit 属性原文（`memdiff/data/prelink_bind_probe/board/proc_TIFSDaemon_979_unit_show.stdout`）：

```text
Id=org.tizen.tv.factory-service.service
Type=simple
Restart=always
User=
Group=
SmackProcessLabel=
CapabilityBoundingSet=cap_chown cap_dac_override cap_dac_read_search cap_fowner cap_fsetid cap_kill cap_setgid cap_setuid cap_setpcap cap_linux_immutable cap_net_bind_service cap_net_broadcast cap_net_admin cap_net_raw cap_ipc_lock cap_ipc_owner cap_sys_module cap_sys_rawio cap_sys_chroot cap_sys_ptrace cap_sys_pacct cap_sys_admin cap_sys_boot cap_sys_nice cap_sys_resource cap_sys_time cap_sys_tty_config cap_mknod cap_lease cap_audit_write cap_audit_control cap_setfcap cap_mac_override cap_mac_admin cap_syslog cap_wake_alarm cap_block_suspend cap_audit_read 0x26 0x27 0x28
TriggeredBy=factory-init.path
Requires=dbus.service system.slice
After=dbus.service system.slice factory-init.path
```

正反向依赖原文分别在每个 `proc_*_unit_dependencies.stdout` 与 `proc_*_unit_reverse.stdout`。`aaa_tvs_deamon.service` 是 `sysinit.target` 的 WantedBy 项，主进程由 `tvs-daemon.sh` 拉起；`org.tizen.tv.factory-service.service` 被 `comss.service` 与 `comss.timer.service` RequiredBy，并受 `factory-init.path` 触发（`board/tvs_direct_dependents.stdout`、`tifs_direct_dependents.stdout`）。这两项不能仅凭静态依赖认定单独重启安全；**本轮结论均为“不确认可安全单独重启”**。`tv-viewer` 和 `launchpad-loader` 位于 `init.scope`，`systemctl status PID` 明确提示没有已加载的独立 unit；两者的父进程都是 PID 260 `launchpad-process-pool`，其父进程是 PID 249 `/bin/sh /usr/bin/launchpad-process`（`board/ps_ef.stdout`、`parent249_cgroup.stdout`）。对这两项不存在可直接按进程名重启的独立 systemd unit，本轮也没有尝试停止或拉起。

## 5. 加载器诊断

`/bin/true` 存在；`LD_DEBUG=libs /bin/true` 成功运行，原始输出在 `board/ld_debug_true.stdout`，前 40 行如下（本次总行数 25，不足 40 行）：

```text
      3254:	find library=libc.so.6 [0]; searching
      3254:	 search cache=/etc/ld.so.cache
      3254:	  trying file=/usr/lib/libc.so.6
      3254:	
      3254:	find library=libgcc_s.so.1 [0]; searching
      3254:	 search cache=/etc/ld.so.cache
      3254:	  trying file=/usr/lib/libgcc_s.so.1
      3254:	
      3254:	
      3254:	[vdprelink failed] /bin/true: not prelinked
      3254:	
      3254:	calling init: /lib/ld-linux.so.3
      3254:	
      3254:	
      3254:	calling init: /usr/lib/libc.so.6
      3254:	
      3254:	
      3254:	calling init: /usr/lib/libgcc_s.so.1
      3254:	
      3254:	
      3254:	initialize program: /bin/true
      3254:	
      3254:	
      3254:	transferring control: /bin/true
      3254:	
```

出现 **`[vdprelink failed] /bin/true: not prelinked`**，所以有预链接相关诊断；本次没有出现 `prelink checking: ok/failed`。`/bin/true` 本身未预链接，不能由此判断四个目标服务的预链接有效性。没有对它们执行 LD_DEBUG 或重启。

## 判断边界

本轮证实了 `/opt/usr` 同分区小文件 bind mount 与恢复可行，并取得了四个进程的当前静态/内存基线。**尚未验证**把库绑定到系统路径、加载器是否接受预链接副本、目标服务可安全单独重启，或内存收益。尤其 `launchpad-loader` 的 AT_SECURE=1 需要在实验设计中单独考虑。全部结论只适用于上述 BUILD_ID 与本次开机；本轮没有对系统目录文件做 bind mount。
