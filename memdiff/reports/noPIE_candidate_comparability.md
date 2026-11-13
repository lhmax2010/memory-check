# noPIE 四组内存候选的离线可比性核查

日期：2026-11-13（Asia/Shanghai）。对象是 GCC、LLVM 第三轮、BUILD_ID `T-KSU2EJAKUC-0101-PERF-202611120549` 的 noPIE 镜像各两次快照。以下 KiB 均为逐映射 `Pss+SwapPss`；固定 C 指六次均有一个实例的 94 个 `(comm, exe)` 身份。文件 PSS 是会计贡献，不等于移除该文件后可回收的物理内存。输入快照及 SHA256 见 [原始输入清单](../data/noPIE_memory_delta_reconciliation/inputs.tsv)与[本轮引用表](../data/noPIE_candidate_comparability/input_refs.tsv)。

| 对象 | 决定 | 已有证据及解释范围 | 下一步；是否需板端 |
|---|---|---|---|
| `libpisa-ipc.so` | **缺少具体材料** | 固定 C 的同路径、同 5 个加载身份，noPIE−GCC +458 KiB 全在 r-x PSS；`.text` 大 405,572 B。GCC/LLVM3 包名版本发行号相同，源码及构建记录未证明相同。[逐映射](../data/noPIE_candidate_comparability/focus_C_mappings.tsv)、[ELF](../data/noPIE_candidate_comparability/focus_elf.tsv) | 先取三版实际 RPM 的 SOURCERPM、源码 revision/patch 清单及编译/链接日志；再决定可控实验。不需板端补测即可补构建证据。 |
| `argot → tsr` 路径族 | **缺少具体材料** | noPIE 两次父子链确实存在，旧四次已测台账无同身份；+13,158 KiB 是运行进程集合差异，不是同程序回退。链首启动条件和角色未确定。[父子台账](../data/noPIE_memory_hotspot_analysis/argot_capture_audit.tsv) | 需当前镜像的 unit/manifest/启动配置、对应包元数据与启动日志，以及旧镜像同类启动状态记录；本轮不建议停服务。现有文件不足，若本机未存须在后续单独补证。 |
| `libvorbisenc.so.2` | **已解释** | GCC 全部已测进程 0 个映射，LLVM3/noPIE 各 19 个；三版 `libsndfile` 加载者与新两版 `libvorbisenc` 加载者重合。LLVM3/noPIE 的 `libsndfile` 直接 `DT_NEEDED libvorbisenc.so.2`，GCC 版没有。[加载者](../data/noPIE_candidate_comparability/all_measured_mappers.tsv)、[动态段](../data/noPIE_candidate_comparability/focus_elf.tsv) | 加载集合差异已定位到最终 ELF 依赖。尚不知产生额外依赖的链接原因及功能是否实际使用，不安排去依赖实验；不需板端解释这项会计差。 |
| `avocd` | **已解释** | noPIE 相对 LLVM3 自身文件 +80 KiB，但整个进程 **−310 KiB**；文件内 r-x +144、r-- −64 KiB，且两版 EXEC/DYN 与预链接状态不同。这是文件映射分项排序，不是该进程的净回退。[逐映射](../data/noPIE_candidate_comparability/focus_C_mappings.tsv)、[进程](../data/noPIE_memory_hotspot_analysis/C_processes_six.tsv)、[ELF](../data/noPIE_candidate_comparability/focus_elf.tsv) | 底层 r-x 驻留或 PSS 分摊原因未单独定因，但不足以列为优化实验；无需板端。 |

**实验方案数：0。** 这四项中没有同时具备同源码/运行条件可比性、明确构建位置和隔离变量的候选。此决定只针对本轮四组，不意味着这些包没有优化空间。noPIE 同时含 noPIE、LTO、MLGO；不将跨镜像差值归因其中任何单一选项。若将来面向保留 PIE 的产品基线开展实验，须在 PIE+LTO+MLGO 镜像重新确认适用性。

## 1. libpisa-ipc：同路径增量，但构建原因未定

| 镜像 | 两次固定 C 文件值 | r-x PSS 两次 | `.text` 字节 | r-x LOAD 文件字节 | `.dynsym` / `.dynstr` 字节 | 包版本发行号 |
|---|---:|---:|---:|---:|---:|---|
| GCC | 1003 / 1001 | 923 / 921 | 479,996 | 1,005,748 | 40,720 / 329,855 | `libpisa-ipc-2.10.11-1.armv7l` |
| LLVM3 | 1472 / 1472 | 1392 / 1392 | 885,568 | 1,586,120 | 46,112 / 454,652 | `libpisa-ipc-2.10.11-1.armv7l` |
| noPIE | 1460 / 1460 | 1380 / 1380 | 885,568 | 1,586,120 | 46,112 / 454,652 | 未保存完整 `rpm -qa` 或该文件 `rpm -qf` |

GCC 与 noPIE 的固定 C 文件均值差 +458 KiB，全由 r-x PSS 贡献；r--/rw- 各次为 40/40 KiB，r-x `Private_Dirty` 为 0。五个身份及 r-x 均值差：`TA_native-home` +22、`adagent-service` +32、`bms-service` +22、`dseal` +105、`pisa-service` +277 KiB；合计 +458。五个身份六次都映射同一路径，但共享者总数和页驻留未做全系统唯一页控制，不能把 PSS 差精确归给代码节。LLVM3 与 noPIE 的 `.text`、`.rodata`、`.dynsym`、`.dynstr`、`.rel.dyn` 节字节哈希均一致，r-x LOAD 文件大小也相同；whole ELF SHA/Build ID 不同。三版均无 `.gnu.prelink_undo`、GNU_LIBLIST、GNU_PRELINKED，不能用预链接元数据解释静态增量。[C 台账](../data/noPIE_candidate_comparability/focus_C_mappings.tsv)、[静态表](../data/noPIE_candidate_comparability/focus_elf.tsv)。

旧两版相同 NEVRA 只来自 [GCC 包清单](../data/gcc_baseline/survey/predeployment/rpm.tsv) 与 [LLVM3 包清单](../data/llvm_round3/survey/packages/rpm_qa_sorted.txt)，**不证明源码 revision 和 patch 集一致**。`.comment` 中 GCC 版显示 GCC，LLVM3/noPIE 同时有 GCC、clang 标记；它不能证明整个源码包由哪种编译器编译，更不能证明 LTO/MLGO。限定在本轮已保存包/构建材料的搜索中，未找到该包三版 SOURCERPM 关联、spec、逐 TU 编译命令、最终链接命令或构建日志。因此优化等级、ARM/Thumb、PIC/PIE、LTO/MLGO、visibility、`-ffunction-sections`/`-fdata-sections` 与 `--gc-sections` 的实际组合、`--as-needed` 均**未确定**；本轮不据最终 ELF 反推出实际开关。若要验证静态增加属于同源码编译差异，最少需要三版对应的 RPM header/SOURCERPM、源码 commit 与补丁清单、该包完整 build.log（含编译和链接命令）；若要把 r-x 增量精确拆到节，还需同一次快照的文件页驻留到节映射数据。

## 2. argot、tsr、tsr-bwrap：出现状态明确，启动条件未知

| 路径 | noPIE boot1/boot2 实例数 | Pss+SwapPss boot1/boot2 KiB | 已保存的直接父进程 |
|---|---:|---:|---|
| `/opt/usr/share/argot/.local/bin/tsr` | 2 / 2 | 968 / 968 | 链首 `systemd`；第二实例 `tsr-bwrap` |
| `/opt/usr/share/argot/.local/bin/tsr-bwrap` | 1 / 1 | 164 / 164 | 链首 `tsr` |
| `/usr/apps/com.samsung.tizen.argot/bin/argot` | 1 / 1 | 12040 / 12012 | 第二实例 `tsr` |

两次均是 `systemd → tsr → tsr-bwrap → tsr → argot`，合计 13,172/13,144 KiB，等权均值 13,158 KiB。旧四次已测台账同路径身份均无记录；这不能证明从未运行，旧镜像也装有 `argot`（GCC/LLVM3 均 `0.6.1-1`）和 `com.samsung.tizen.tsr`（GCC `1.0.79-1`、LLVM3 `1.0.96-1`）。noPIE 包 NEVRA、包提供者、unit/manifest、开机触发条件和完整日志未保存在可验证范围。现有 followup 日志的异常摘录未覆盖该链启动事件，不能据此判断为业务、测试或异常常驻。`argot` 已拉回 ELF 的 `.comment` 有 Tizen GCC、Ubuntu GCC、rustc 标记，无 clang 标记；这仅是文件内残留标记，**不证明**整个包的编译来源。[父子/捕获状态](../data/noPIE_memory_hotspot_analysis/argot_capture_audit.tsv)、[ELF](../data/noPIE_candidate_comparability/focus_elf.tsv)、[历史包清单](../data/llvm_round3/survey/packages/rpm_qa_sorted.txt)。

这条链在当前数据中属于**下版基线必须记录并对齐的运行条件**；尚不支持同程序内存优化比较，也不能把 12.85 MiB 当成可回收收益。最少缺口：noPIE 中 `argot`/`tsr` 的 `rpm -qf` 与完整 NEVRA/SOURCERPM；实际安装的 system/user unit 内容、应用 manifest 与链首启动配置；两次 boot 在链首启动时段的完整 journal/dlog 及启动请求；旧 GCC/LLVM3 同等时段的 unit 状态、进程退出与启动日志。前两类定包和配置，日志区分“配置允许”与“本次由谁触发”；旧记录判断是否纯采样时刻或工作负载差。现有 noPIE 两次各 6 个采集中退出 PID 不填零。[覆盖限制](noPIE_memory_delta_reconciliation.md)。

## 3. libvorbisenc：直接依赖解释加载集合，不证明可以删除

| 镜像 | 固定 C 中加载身份数 | C 文件 Pss+SwapPss 两次 KiB | 全部已测 `libsndfile` / `libvorbisenc` 映射进程数 | `libsndfile` 是否直接 NEEDED `libvorbisenc.so.2` |
|---|---:|---:|---:|---|
| GCC | 0 / 0 | 0 / 0 | 21/0，21/0 | 否 |
| LLVM3 | 19 / 19 | 1005 / 1005 | 19/19，19/19 | 是 |
| noPIE | 19 / 19 | 819 / 819 | 19/19，19/19 | 是 |

noPIE 的 819 KiB 中 r-x 15、r-- 728、rw- 76 KiB；GCC C 内 +819 KiB 是从零个映射到 19 个映射。每个 noPIE/LLVM3 `libvorbisenc` 映射者也映射 `libsndfile`。GCC 包清单列出 `libvorbisenc-1.3.7-1.2`，LLVM3 为 `1.3.7-1.11`；GCC 未拉回该 ELF，所以既不能声称它在镜像里不存在，也不能比较其静态节。`libsndfile` GCC 为 `1.2.2-1.1`，LLVM3 为 `1.2.2-1.9`；noPIE 对应 NEVRA 未保存。GCC/LLVM3/noPIE 的 `libsndfile` 都有 28 个 `vorbis_*` 未定义动态符号；在 LLVM3/noPIE 的已拉回 `libvorbisenc` 定义符号中未找到同名项。这提示直接 NEEDED 未必由这些静态符号引用所需，但不排除 `dlsym`、插件或别的运行路径；不能据此宣称 `--as-needed` 安全可删。最终 ELF 依赖链与实际 maps 同向，**仅解释加载差**，无法从现有材料定位为何链接命令产生该 NEEDED，也不把 libvorbisenc 的文件 PSS 当作独立节省额。[全映射检查](../data/noPIE_candidate_comparability/all_measured_mappers.tsv)、[静态 NEEDED/版本](../data/noPIE_candidate_comparability/focus_elf.tsv)、[符号表](../data/noPIE_candidate_comparability/libsndfile_undefined_vorbis.tsv)。

固定 C 中 noPIE 两次每次的 19 个加载身份完全相同：`dotnet-hydra-loader` 的 `DN_g.tizen.menu`、`team-launcher` 的 `TA_native-home`、`aisctrlmgr_server`、`common-daemon-basic-monitor`、`connectivity-common-daemon`、`home-mainhub`、`issue_report_agent`、`org.tizen.easysetup-daemon`、`p2p-asm`、`settings-service`、`speaker-manager`、`tvctx-manager`、`vd-net-config`、`volume-app`、`wrt` 各 53 KiB；`avocd`、`bt-service`、`launchpad-loader`、`pulseaudio` 各 6 KiB；总计 819 KiB。各身份实际完整 `(comm, exe)` 键、两次的 Pss 与 SwapPss 见 [逐映射汇总](../data/noPIE_candidate_comparability/focus_C_mappings.tsv)。这里的 53/6 KiB 是逐进程 PSS 分摊，不能相加成一个库的物理唯一驻留后宣称独立收益。

## 4. avocd：文件增加与进程净变化方向相反

| 镜像 | 自身 ELF Pss+SwapPss 两次 KiB | r-x Pss | r-- Pss | rw- Pss+SwapPss | 整个进程 Pss+SwapPss 两次 KiB |
|---|---:|---:|---:|---:|---:|
| GCC | 924/916 | 896/892 | 4/4 | 24/20 | 7062/7057 |
| LLVM3 | 1152/1152 | 1064/1064 | 68/68 | 20/20 | 7627/7630 |
| noPIE | 1232/1232 | 1208/1208 | 4/4 | 20/20 | 7311/7326 |

noPIE−LLVM3 的文件差 +80 KiB 分成 r-x +144、r-- −64、rw- 0；文件的 SwapPss 两次均为 4 KiB，因此 +80 都是 Pss。**整个进程**却从 7627/7630 降至 7311/7326，均值 7628.5→7318.5，差 **−310 KiB**；其中 Pss 均值 6102.5→5576.5（−526），SwapPss 1526→1742（+216）。这不足以把 `avocd` 自身文件的 +80 排名视为整个服务回退。[文件逐映射](../data/noPIE_candidate_comparability/focus_C_mappings.tsv)、[进程原表](../data/noPIE_memory_hotspot_analysis/C_processes_six.tsv)。

三版 `avoc-daemon` 的可得包版本发行号均 `0.1.0-1`；noPIE `rpm -qf` 由已有记录确认，源码 revision/patch 集未证实相同。LLVM3 文件为 DYN、无预链接标记；noPIE 文件为 EXEC、带 `.gnu.prelink_undo` 和 GNU_LIBLIST，Build ID/whole ELF 哈希不同。`.text` 1,274,276→1,276,590 B（+2314 B），`.rodata` 342,296→410,440 B（+68,144 B），r-x LOAD 文件字节 2,294,044→2,293,156（−888 B）。这些静态变化不能直接换算驻留页，且整进程净方向相反；本轮**不安排**为解释 +80 KiB 而改构建或上板。若以后要定因 r-x PSS，需要相同源 revision/patch、逐包链接日志、同条件页到节驻留及全部映射共享者记录；当前不影响本项结束。[静态表](../data/noPIE_candidate_comparability/focus_elf.tsv)。

## 取证边界和报告修正

本轮只对 94 身份已分类 VMA 中的四组路径做重算，另对六次已测进程的 `libsndfile`/`libvorbisenc` 映射做限域检查；没有重做全系统热点排名。14 份可得目标 ELF 的 SHA256 均与拉回记录一致；61 条 readelf 命令返回码均为 0。执行命令、退出码、进度与校验见 [命令表](../data/noPIE_candidate_comparability/readelf_commands.tsv)、[运行日志](../data/noPIE_candidate_comparability/run_console.log)、[校验](../data/noPIE_candidate_comparability/validation.json)。旧版预链接后的板端副本与原始 RPM 不是同一阶段；本轮没有用缺失的 RPM 原件替代它。

[热点报告](noPIE_memory_hotspot_analysis.md)中 `libpisa-ipc` 同源码/参数未知、`argot` 角色未知、`libvorbisenc` 是加载集合差异的限定仍正确，无需改数值。该报告的 `avocd` GCC 比较为另一基线；**本轮 LLVM3→noPIE 的自身文件 +80 KiB 不能被解读成整进程回退**。建议周报保留进程净值与文件分项两个口径并列。旧报告无需自动改写。已采集进程外的未知内存、noPIE 退出 PID、跨镜像采样时刻及共享页 PSS 分摊仍是边界。[总量分解](noPIE_memory_delta_reconciliation.md)。

复现：

```sh
ulimit -v 2500000
taskset -c 0 nice -n 19 ionice -c3 python3 memdiff/scripts/nopie_candidate_comparability.py \
  --prior memdiff/data/noPIE_memory_hotspot_analysis \
  --manifest memdiff/data/noPIE_memory_delta_reconciliation/input_manifest.json \
  --out memdiff/data/noPIE_candidate_comparability
```
