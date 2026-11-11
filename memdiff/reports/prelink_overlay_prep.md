# KantSU2E 板预链接验证准备：overlay 审计与进程收益拆分

采集日期 2026-11-11。板子 IP `192.168.108.26`；`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`，与上次 LLVM bind 自检记录一致。`armv7l`、`NT72671D`、KSU2E dtsversion、clang 内核与 BUILD_ID 的门禁逐项通过，原文及判定在 [`board/identity_checks.json`](../data/prelink_overlay_prep/board/identity_checks.json) 和同目录 `identity_*.stdout`。初始/最终 boot_id 均为 `0d30d3eb-a65b-44e2-b1d6-ee93e2c39af5`；采集前 UID=5001，临时 root 采集后 `sdb root off`，最终 UID=5001（`board/uid_restored_0.stdout`、`boot_id_restored.stdout`、`final_state.stdout`）。板上没有创建或修改文件，也没有重启；开发机任务以 `taskset -c 0 nice -n 19` 串行运行，脚本不读终端输入。

## 一、overlay 现状

### 挂载与目录清单

`/proc/mounts` 中所有 overlay 的原始输出为 [`board/proc_mounts.stdout`](../data/prelink_overlay_prep/board/proc_mounts.stdout)，提取表为 [`overlay_mounts.json`](../data/prelink_overlay_prep/overlay_mounts.json)：

| 挂载点 | lowerdir | upperdir | workdir |
| --- | --- | --- | --- |
| `/` | `/` | `/opt/.overlay/platform/upperdir` | `/opt/.overlay/platform/workdir` |
| `/factory_peq` | `/factory_peq` | `/opt/.overlay/factory_peq/upperdir` | `/opt/.overlay/factory_peq/workdir` |
| `/prd` | `/prd` | `/opt/.overlay/prd/upperdir` | `/opt/.overlay/prd/workdir` |

`/opt/.overlay` 下找到 3 个 upperdir：`factory_peq` 与 `prd` 各只含 upperdir 本身；`platform` 在**可读范围内**有 105 个条目（36 目录、55 常规文件、14 字符设备）。全部路径、大小、修改时间、类型及模式在 [`upper_inventory.tsv`](../data/prelink_overlay_prep/upper_inventory.tsv)。`find -xdev` 遍历 `/opt/.overlay/platform/upperdir/zone/securezone` 返回 Permission denied（`upper_find_errors.tsv` 及 `board/upper1_inventory.stdout`）；因此不能声称对该目录内部完成清点。该不可读目录位于 `/zone`，不在本任务指定的四类系统 ELF 路径下。

14 个字符设备均为 **major/minor=0/0**，位于 `/etc/emanual_icon/*.png`；逐项见 [`upper_whiteouts.tsv`](../data/prelink_overlay_prep/upper_whiteouts.tsv) 和 `board/upper1_whiteouts.stdout`。把它们当作 overlay 删除标记，不当作普通 PNG 文件。

### 与原始根文件对比、ELF 覆盖

对可读的全部 55 个 upperdir 常规文件，按实际叠加路径映射到 `/.org_rootfs` 下同路径；`/prd` 映射到 `/.org_rootfs/prd`，`/factory_peq` 映射到 `/.org_rootfs/factory_peq`。逐文件的 upper/lower 字节数与 SHA256 在 [`upper_file_comparisons.tsv`](../data/prelink_overlay_prep/upper_file_comparisons.tsv)，命令输出为 `board/upper*_compare.stdout`。结果：**6 个与 lower 完全相同、2 个不同、47 个 lower 中没有同路径常规文件**。不同的是 `/etc/shadow` 与 `/etc/shadow-`；只比较哈希和大小，没有读取其内容。`/prd` 和 `/factory_peq` 的 upperdir 没有常规文件。

指定目录 `/usr/lib`、`/usr/bin`、`/lib`、`/prd/usr/lib` 的 upperdir 内**没有被覆盖的 ELF 文件（0 个）**。在这些目录下可读的 39 个常规文件均位于 `/usr/bin/target_view/python3/.../__pycache__/`，ELF 魔数 `7f 45 4c 46` 检查均未命中；无符号链接。逐文件前 4 字节及判定在 [`upper_elf_magic.tsv`](../data/prelink_overlay_prep/upper_elf_magic.tsv)。不可读的 `/zone/securezone` 不影响上述四个路径的枚举结论。

### 时间线索与可能遗留

当前镜像 BUILD_ID 尾部为 `202611061751`，**时区未在 BUILD_ID 中编码**；[`timeline.json`](../data/prelink_overlay_prep/timeline.json) 仅为筛选，把它临时按板上 `-0800` 时区解释。`/.org_rootfs/etc/os-release` 修改时间为 `2026-11-06T01:43:00-08:00`（`board/original_os_release_stat.stdout`），本次开机时间按板上日期减 uptime 约为 `2026-11-11T00:21:09.660000-08:00`（`board/board_date.stdout`、`board/board_uptime.stdout`）。在 69 个非目录条目中，分别有 **66** 个早于假定 BUILD_ID 时刻、**66** 个早于原始 os-release mtime、**67** 个早于本次开机。每个条目的三项判断和时间都在 [`upper_age_flags.tsv`](../data/prelink_overlay_prep/upper_age_flags.tsv)。

需要人工留意的路径：`/root/.bash_history`（2026-11-11 00:20:06 -0800，lower 无同路径文件）、`/usr/bin/target_view/python3/.../__pycache__/` 下 39 个 `.pyc`（mtime 显示 1969-12-31，lower 无同路径文件）、不同于 lower 的 `/etc/shadow`（mtime 显示 1969-12-31）及 `/etc/shadow-`（2026-11-06 01:34:56 -0800）。路径、大小、时间与哈希证据见上述 inventory/comparison 表。**这些是可能的运行期或历史遗留，不能仅凭 mtime 证明跨刷机保留或手动安装；1969 时间尤其可能来自开机早期未校时。**没有发现名称直接指向 prelink/TPMS/memdiff 实验的 upperdir 文件。刷机实际完成时间未保存，BUILD_ID 和原始文件 mtime 只是线索。

## 二、三个进程的离线 Private_Dirty 拆分

只读取 GCC boot1/boot2、第三轮 LLVM boot1/boot2 的 `02_steady/smaps_raw.txt.gz`，具体四个路径见 [`sources.json`](../data/prelink_overlay_prep/sources.json)。进程按 smaps 头中的 comm 与 exe 配对。a/b 是主程序**文件映射**的 `r--`/`rw-`；c/d 是路径含 `.so` 的库**文件映射**的 `r--`/`rw-`；e 是无路径、`[heap]`、`[anon...]`、`[stack...]`、`[tstack...]`；其余均归 f，包括主程序/库的 `r-x` 与其他文件。所有值均为 Private_Dirty KiB，差值为 LLVM 两次均值减 GCC 两次均值，逐次原表 [`components_per_boot.tsv`](../data/prelink_overlay_prep/components_per_boot.tsv)。分类互斥，未把匿名页重复计入文件映射。

| 进程 | 类别 | GCC1 | GCC2 | LLVM1 | LLVM2 | GCC 均值 | LLVM 均值 | 差值 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tvs-daemon | exe_r-- | 4 | 4 | 8 | 8 | 4.0 | 8.0 | 4.0 |
| tvs-daemon | exe_rw- | 4 | 4 | 4 | 4 | 4.0 | 4.0 | 0.0 |
| tvs-daemon | so_r-- | 1084 | 1072 | 2056 | 2056 | 1078.0 | 2056.0 | 978.0 |
| tvs-daemon | so_rw- | 332 | 192 | 1140 | 1144 | 262.0 | 1142.0 | 880.0 |
| tvs-daemon | anonymous | 3696 | 2688 | 1804 | 1492 | 3192.0 | 1648.0 | -1544.0 |
| tvs-daemon | other | 16 | 12 | 12 | 12 | 14.0 | 12.0 | -2.0 |
| tv-viewer | exe_r-- | 4 | 4 | 40 | 40 | 4.0 | 40.0 | 36.0 |
| tv-viewer | exe_rw- | 4 | 4 | 4 | 4 | 4.0 | 4.0 | 0.0 |
| tv-viewer | so_r-- | 984 | 984 | 2388 | 2388 | 984.0 | 2388.0 | 1404.0 |
| tv-viewer | so_rw- | 72 | 48 | 32 | 56 | 60.0 | 44.0 | -16.0 |
| tv-viewer | anonymous | 1036 | 840 | 600 | 804 | 938.0 | 702.0 | -236.0 |
| tv-viewer | other | 20 | 24 | 16 | 16 | 22.0 | 16.0 | -6.0 |
| TIFSDaemon | exe_r-- | 4 | 4 | 12 | 12 | 4.0 | 12.0 | 8.0 |
| TIFSDaemon | exe_rw- | 4 | 4 | 4 | 4 | 4.0 | 4.0 | 0.0 |
| TIFSDaemon | so_r-- | 792 | 792 | 1952 | 1952 | 792.0 | 1952.0 | 1160.0 |
| TIFSDaemon | so_rw- | 36 | 36 | 36 | 52 | 36.0 | 44.0 | 8.0 |
| TIFSDaemon | anonymous | 276 | 276 | 284 | 352 | 276.0 | 318.0 | 42.0 |
| TIFSDaemon | other | 4 | 8 | 4 | 4 | 6.0 | 4.0 | -2.0 |

下表把 a+b+c+d 合计与同一份逐映射 smaps 求和的进程总 Pss+SwapPss 并列。`占比` 只是两个**不同指标的差值之比**，不能作为 Pss+SwapPss 的严格组成分解。用户指定的“预期可收回量”按 a+b+c+d 的私脏差额列为**候选上限**；它还包含两边库集合、布局和运行时写入差异，不能当作恢复预链接后的实测收益。

| 进程 | GCC a+b+c+d（boot1/2）KiB | LLVM a+b+c+d（boot1/2）KiB | 候选差额 KiB | 总 Pss+SwapPss 差 KiB | 数值比 |
| --- | ---: | ---: | ---: | ---: | ---: |
| tvs-daemon | 1424 / 1272 | 3208 / 3212 | 1862.0 | 6603.5 | 28.2% |
| tv-viewer | 1064 / 1040 | 2464 / 2488 | 1424.0 | 2272.5 | 62.7% |
| TIFSDaemon | 836 / 836 | 2004 / 2020 | 1176.0 | 1113.5 | 105.6% |

完整逐映射 Pss/SwapPss/Private_Dirty 中间表为 [`components_per_boot.tsv`](../data/prelink_overlay_prep/components_per_boot.tsv)，均值/极差为 [`components_summary.tsv`](../data/prelink_overlay_prep/components_summary.tsv)，总量和候选比值为 [`file_dirty_vs_total.tsv`](../data/prelink_overlay_prep/file_dirty_vs_total.tsv)。总 Pss+SwapPss 采用逐映射相加，不与 `smaps_rollup` 混用；逐映射页级舍入使它与既有 rollup 报告的数值略异。

### 映射库集合差异

下表对每侧两次开机的 `.so` 路径取并集再比较；逐次配对差集在 [`library_set_differences.tsv`](../data/prelink_overlay_prep/library_set_differences.tsv)，四次各自的完整集合在 [`library_sets.tsv`](../data/prelink_overlay_prep/library_sets.tsv)。

| 进程 | 哪侧独有 | 库路径 |
| --- | --- | --- |
| tvs-daemon | GCC_only | `/usr/lib/libdemux-control.so.0.1` |
| tvs-daemon | GCC_only | `/usr/lib/libgst-ext-lib.so.0.1.0` |
| tvs-daemon | GCC_only | `/usr/lib/libpsl.so.5.3.2` |
| tvs-daemon | GCC_only | `/usr/lib/libpvr-control.so` |
| tvs-daemon | LLVM_only | `/usr/lib/libappcore-agent.so.1.7.5` |
| tv-viewer | GCC_only | `/usr/lib/libpsl.so.5.3.2` |
| TIFSDaemon | GCC_only | `/usr/lib/libpsl.so.5.3.2` |

这些不相同的库集合会影响 c/d 与总进程内存差的解释，尤其 tvs-daemon 还存在 GCC boot1 仅当次加载的库。不能把 a+b+c+d 差额全部归因于预链接状态。

## 三、当前 LLVM 镜像的预链接输入清单

按本次三个 PID 的 `/proc/PID/maps` 中去重 `.so` 文件路径建立各自闭包：tvs-daemon **297** 个、tv-viewer **336** 个、TIFSDaemon **304** 个；三者**并集 480 个**。原始 maps 与每批命令返回码在 `board/proc_*_maps.*`、`board/closure_metadata_*.json`；路径集合 [`process_closures.json`](../data/prelink_overlay_prep/process_closures.json)，各进程成员表 [`closure_membership.tsv`](../data/prelink_overlay_prep/closure_membership.tsv)。每个库的路径、板上 SHA256、`rpm -qf` 原样包名版本、ELF e_type 与是否落在 prelink.conf 目录，在 [`library_union.tsv`](../data/prelink_overlay_prep/library_union.tsv)。

从当前 [`/etc/prelink.conf`](../data/prelink_overlay_prep/board/prelink_conf.stdout) 的 8 个 `-l` 目录按路径前缀判断，并集中 **6 个库不在所列目录**：

| 库路径 | `rpm -qf` 结果 |
| --- | --- |
| `/hal/lib/bufmgr/libbuffer-control.so` | `buffer-control-2.0.2-1.armv7l` |
| `/hal/lib/bufmgr/libhal-backend-tbm-entry.so.2.1.0` | `hal-backend-tbm-2.1.0-2.armv7l` |
| `/hal/lib/libcamera-control.so` | `camera-control-0.1.1-0.armv7l` |
| `/opt/usr/apps/Ddrm/fkp/lib/libfkpInternal.so` | `fkp-26.09.29.0-1.armv7l` |
| `/usr/share/appcore/plugins/libappcore-plugin.so` | `app-core-extension-1.3.7-1.armv7l` |
| `/usr/share/appcore/plugins/libappcore-ui-plugin.so` | `app-core-extension-1.3.7-1.armv7l` |

一个例外：`/usr/lib/libc-2.40.so` 可读取并已记录 SHA256/ET_DYN，但 `rpm -qf` 原路径返回未归属；`/usr/lib/libc.so.6` 符号链接由 `glibc-2.40-1.72.armv7l` 归属，证据 [`board/libc_rpm_followup.stdout`](../data/prelink_overlay_prep/board/libc_rpm_followup.stdout)。清单保留原路径的 `NOT_OWNED`，不以符号链接查询替换它。

## 适用边界与复核

本轮没有修改任何板上文件、服务、挂载或构建配置。`/zone/securezone` 的 MAC/权限限制使“全部 upperdir”在这一子树内不完整；报告中关于指定四类系统 ELF 路径的 0 个结论仍覆盖了这些路径。年龄标记不能证明刷机后保留。恢复预链接能否收回上表私脏差额，需要用实验镜像/实际预链接库并按相同采集流程验证；本轮只给准备清单和观察到的差值。
