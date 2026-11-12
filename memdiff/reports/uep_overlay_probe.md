# GCC KantSU2E 板 UEP 与 overlay 写入探测

采集日期：2026-11-12（原始日志时间为 UTC）。板子 `192.168.108.26`，用户于本轮再次确认 IP。**本轮只探测一个不在运行的工具，没有运行预链接撤销或内存实验。**

## 身份和探测对象

`uname -m=armv7l`，设备型号含 `NT72671D`，cmdline 的 `dtsversion` 含 `KSU2E`，内核由 GCC 编译，`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202610010416`，开机 ID `97c290b7-727f-4055-acbb-525ae5c7e134`。身份核对及命令返回码见 [`identity.json`](../data/uep_overlay_probe/identity.json) 和 [`raw/identity.*`](../data/uep_overlay_probe/raw/)。

选用 `/usr/bin/whoami`：位于要求的 `/usr/bin`，当前 `/proc/*/maps` 无映射者，`/etc` 与 `/usr/lib/systemd/system` 的递归精确路径搜索没有引用；不是 19 个预链接目标；交叉 readelf 的节表/动态段没有预链接标记；原版 `--version` 返回 0 且快速退出。探测前 upper 中没有它，`/.org_rootfs/usr/bin/whoami` 和合并视图的 SHA256 均为 `2b5e24b28f30a4a7bd5eb8a34f2cdfcf69f199ea36e187370140aabfb1bf1604`。理由与每项返回码见 [`selected_candidate.json`](../data/uep_overlay_probe/selected_candidate.json) 和 [`raw/candidate_whoami_*`](../data/uep_overlay_probe/raw/)。平台交叉 readelf 的 `.comment` 为文件偏移 `0x40d8`、大小 `0x2c`、无 `A`（ALLOC）标志；修改的是该节首字节 `G→H`，文件大小 17,968 字节，其他字节未变。原件及单字节对照文件、节表均保存在 [`data/uep_overlay_probe/`](../data/uep_overlay_probe/)。

## 四项直接结果

| 探测 | 结果 | 证据 |
|---|---|---|
| `/root/uep_probe/getfattr` 未签名程序直接执行 | **是**；`--version` 返回 0，输出 `getfattr 2.5.1`；读取 tvs-daemon 扩展属性返回 0 | [`attr_probe.json`](../data/uep_overlay_probe/attr_probe.json)，[`raw/direct_*`](../data/uep_overlay_probe/raw/) |
| 通过 `/lib/ld-linux.so.3` 执行同一程序 | **是**；版本和扩展属性读取均返回 0 | 同上 `loader_*` |
| `/usr/bin/whoami` 原样覆盖触发 overlay copy-up 后执行 | **是**；upper 文件出现，SHA256 与下层原件完全相同，`--version` 返回 0，输出与基准一致 | [`mutation_state.json`](../data/uep_overlay_probe/mutation_state.json)，[`raw/same_*`](../data/uep_overlay_probe/raw/) |
| 仅改 `.comment` 一个字节后执行 | **是**；文件 SHA256 变为 `775773bd9c6099da7dec9c840569fc2218aed4457b87ba9830e2b75840b6c591`，与本机单字节对照件一致；`--version` 返回 0，输出仍与基准一致 | [`mutation_state.json`](../data/uep_overlay_probe/mutation_state.json)，[`raw/modified_*`](../data/uep_overlay_probe/raw/) |
| 原地覆盖后的扩展属性保持 | **是**；原件、原样 copy-up、单字节改动、写回原件四次 `getfattr -d -m - -e hex` 都只有 `security.SMACK64=0x5f`，属主 `0:0`、权限 `755`、getcap 空、chsmack `access="_"` 均一致 | [`mutation_state.json`](../data/uep_overlay_probe/mutation_state.json)，[`raw/before_*`](../data/uep_overlay_probe/raw/)、`same_*`、`modified_*`、`restored_*` |

`getfattr/setfattr` 二进制来自官方 Tizen Base 快照的 `attr-2.5.1-1.87.armv7l.rpm`，只临时放在 `/root/uep_probe/`，没有安装 RPM。来源 URL 与 RPM SHA256 见 [`prelink_undo_ab.md`](prelink_undo_ab.md)；本机二进制 SHA256 分别为 `087edcfd99b584b37a1e84f73c535cc5e0b46f96c0242c84a52fc44598dda438`、`d93671b20cf3e6fe29238d468566b90ffa7a0c72389d87ae83e00fc69750fa4d`。`setfattr` 还在 `/root/uep_probe/` 的临时文件上通过了添加、读取、删除 `user.uep_probe` 的自检；见 [`raw/mutation_attr_test.stdout`](../data/uep_overlay_probe/raw/mutation_attr_test.stdout)。

各阶段前后完整 dmesg、dlog main/system 原文保存在 `raw/*_{before,after}_{dmesg,dlog_main,dlog_system}.stdout`。逐行多重集比较的 12 组结果中，与签名、UEP、kUEP、完整性有关的新增行均为 0；见 [`log_delta_summary.json`](../data/uep_overlay_probe/log_delta_summary.json) 和 [`uep_log_delta.tsv`](../data/uep_overlay_probe/uep_log_delta.tsv)。日志为环形缓冲区，故此项只说明**保存的前后快照没有观察到新增匹配行**，不能单独证明校验未运行。

## 恢复与结论边界

已用原地覆盖写回原字节；SHA256、属主、权限、getcap、chsmack、全部可枚举扩展属性和 `--version` 输出均与基准一致。`/root/uep_probe/` 已删净；未重启，boot ID 未变；`sdb root off` 后 UID 为 5001，普通 UID 下 `whoami --version` 仍返回原版第一行。见 [`mutation_state.json`](../data/uep_overlay_probe/mutation_state.json)、[`raw/mutation_stage_cleanup.*`](../data/uep_overlay_probe/raw/)、[`post_probe_sdk.stdout`](../data/uep_overlay_probe/post_probe_sdk.stdout)。按用户指定的成功恢复路径，upper 中仍留有**与原件字节和已核对属性一致**的 `/usr/bin/whoami` 副本；没有直接删除 upper，也没有触发失败恢复分支的重启。

**有数据支撑：**这个工具在当前镜像上可从 `/root` 运行临时未签名二进制；原样 copy-up 和只改非 ALLOC `.comment` 字节后都可执行；overlay copy-up 保留了本文件已枚举的扩展属性。

**未确定：**撤销预链接会改动 ELF 的加载相关内容，其 UEP 结果不能从仅改 `.comment` 的试验推出。`whoami` 也不代表 19 个目标程序或带预链接标记的库；本轮没有替换这些文件、重启服务或测量内存。因而“把撤销版放入 overlay 的完整实验路线可行”仍需对目标文件的备份/属性恢复、签名处理和服务健康另作放行检查。

执行记录中的首次准备运行因 `sdb shell` 的传输返回码没有反映远端 `grep` 退出码而误判候选为空；脚本改为显式 `__UEP_RC__` 后重新运行，板上此前仅做过只读命令及临时工具清理。两次尝试和最终结束状态均保存在 [`prepare_console.log`](../data/uep_overlay_probe/prepare_console.log) 与 [`progress.log`](../data/uep_overlay_probe/progress.log)。所有脚本不读终端输入，逐步写日志并打印 `已结束 时间 状态`。
