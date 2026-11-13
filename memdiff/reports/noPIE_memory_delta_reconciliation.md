# noPIE 新镜像整体 Pss+SwapPss 差值分解

采集数据来自 GCC 与第三轮 LLVM 各两次 `02_steady/smaps_raw.txt.gz`、noPIE 新镜像两次 `image_budget` 原始 per-PID smaps。**没有使用 11 月 11 日的单次代码页数据。**本轮只作整体进程内存的会计分解，没有连接板子、重新采集或运行 HEVC。全部数值单位为 KiB；MiB = KiB / 1024。可重跑的输入与 SHA256 在 [inputs.tsv](../data/noPIE_memory_delta_reconciliation/inputs.tsv)，新镜像逐 PID 原始文件的 SHA256 在 [new_image_raw_files.tsv](../data/noPIE_memory_delta_reconciliation/new_image_raw_files.tsv)。输入清单是 [input_manifest.json](../data/noPIE_memory_delta_reconciliation/input_manifest.json)，脚本是 [nopie_memory_delta_reconciliation.py](../scripts/nopie_memory_delta_reconciliation.py)。

## 结论

noPIE 相对第三轮 LLVM，固定 94 身份的均值差 **−26,145 KiB（−25.532 MiB）**，全部已采集用户进程的均值差 **−12,781 KiB（−12.481 MiB）**。两者相差的 **+13,364 KiB（+13.051 MiB）** 是固定集合以外进程 `R` 的已采集 Pss+SwapPss 净贡献；不是两张表混了不同快照或 PSS 口径。R 中，noPIE 两次均采到、第三轮 LLVM 两次均未采到的 `argot` **+12,026 KiB**，同路径族的 `tsr` **+968 KiB**、`tsr-bwrap` **+164 KiB**，合计 **+13,158 KiB**，占 R 净差的 **98.46%**。其余确认双方有记录的身份合计 **−435.5 KiB**；涉及采集缺口、不能把缺席视作已确认的身份在“已采集台账”中净贡献 **+641.5 KiB**。三者精确相加为 +13,364 KiB。`argot` 路径族是路径上的归组，不据此断言父子关系或独立内存收益。证据：[remaining_contributions.tsv](../data/noPIE_memory_delta_reconciliation/remaining_contributions.tsv)、[remaining_categories.tsv](../data/noPIE_memory_delta_reconciliation/remaining_categories.tsv)、[validation.json](../data/noPIE_memory_delta_reconciliation/validation.json)。

相对 GCC 的 R 净差为 **−3,197 KiB**：noPIE 新采到的身份贡献 +16,043 KiB，双方采到但不满足六次唯一实例条件的身份 +1,119.5 KiB，涉及缺席无法确认的身份在已采集台账中 −20,359.5 KiB。GCC 两次的 `perception-engine` **16,988/16,881 KiB**、`acm-service` **4,619/4,620 KiB** 在 noPIE 已采集用户进程表中均未出现；它们的会计贡献分别是 −16,934.5、−4,619.5 KiB，合计 −21,554 KiB。但 noPIE 两次各有 6 个采集期间退出、身份不可恢复的 PID，所以本报告不把这一点表述为两个服务在整个开机期间确定未运行。`bnr-service` 在 noPIE 两次各 2,885 KiB、GCC 未采到；第三轮 LLVM 两次已采到它，故不是 noPIE 相对第三轮 LLVM 的新增解释。完整实例与来源见 [process_ledger.tsv](../data/noPIE_memory_delta_reconciliation/process_ledger.tsv)。

## 口径和覆盖

固定集合 `C` **直接读取上一轮** [strict_common_processes.tsv](../data/noPIE_followup_validation/T-KSU2EJAKUC-0101-PERF-202611120549/20261113_followup/strict_common_processes.tsv)：键为 `(comm/Name, /proc/PID/exe 路径)`，六个快照中每个键各恰好一个实例，共 94 个键、564 条记录。本轮逐条复核后仍为 94 个身份且每快照各 94 个实例；不是仅凭“94”名称推定。相同 comm、不同 exe 分开；同键多实例不进入 C，全部留在 R，PID 只用于同一快照的来源追踪。没有公开命令行参数。历史 parser 的 VMA 正则复用 [historical_same_source.py](../data/noPIE_prelink_validation/historical_same_source.py)；新镜像的 `process_budget.tsv` 逐 PID 对原始 smaps 的 Pss、SwapPss 做精确校验，沿用 [image_budget/budget.py](../tools/image_budget/budget.py) 的已完成进程集合。缺少 `Pss` 或 `SwapPss` 的 VMA 不按 0 处理；实际纳入的 VMA 均有两字段。内核线程无 VMA、无可执行路径且 Pss 为 0，不计入用户进程。六次的 T 都是**成功采到的用户进程**，并非所有瞬时存在进程的完整物理内存。

### 表 1：六次输入和覆盖

| 标签 | 快照日期/时刻 | boot ID | 开机后秒数 | 稳定性 | 清单 PID / 实测用户实例 / 采集失败 PID | 原始与预算 |
|---|---|---|---:|---|---:|---|
| GCC1 | 11-02 19:08:53 | `69265d0d-de28-499e-82d3-a755b6e170f7` | 2763.83 | 等待上限，`steady=no` | 324 / 106 / 0 | `gcc_baseline/boot1/.../02_steady/smaps_raw.txt.gz` |
| GCC2 | 11-02 20:09:00 | `d681b57d-6154-4631-9e55-341a4ea12742` | 2763.06 | 等待上限，`steady=no` | 326 / 104 / 0 | `gcc_baseline/boot2/.../02_steady/smaps_raw.txt.gz` |
| LLVM3-1 | 11-03 02:36:32 | `8b906be1-bd2f-4bc9-a6d4-3141db9d9eea` | 2762.81 | 等待上限，`steady=no` | 319 / 105 / 0 | `llvm_round3/boot1/.../02_steady/smaps_raw.txt.gz` |
| LLVM3-2 | 11-03 03:48:06 | `d4918959-4064-4eaf-b3dd-47b4538f8721` | 2762.27 | 等待上限，`steady=no` | 314 / 103 / 0 | `llvm_round3/boot2/.../02_steady/smaps_raw.txt.gz` |
| noPIE1 | 11-13（采集启动 01:14:35 UTC；精确快照墙钟未记录） | `48c5ccb1-cd54-4b94-b518-2486cf0a0d42` | 823 | `steady=True` | 321 / 106 / 6 | `noPIE_prelink_validation/boots/boot1/collection`、`budget` |
| noPIE2 | 11-13（采集启动 01:50:10 UTC；精确快照墙钟未记录） | `2cf21223-81d9-4623-81da-c556dcf62577` | 799 | `steady=True` | 320 / 105 / 6 | `noPIE_prelink_validation/boots/boot2/collection`、`budget` |

表内路径为 `memdiff/data/` 下的缩写；**实际唯一文件名、SHA256、质量文件及解析脚本 SHA256** 以 [inputs.tsv](../data/noPIE_memory_delta_reconciliation/inputs.tsv) 为准。noPIE BUILD_ID 为 `T-KSU2EJAKUC-0101-PERF-202611120549`；历史四次快照本身未保存 BUILD_ID，不能由内核编译器反推。GCC/LLVM3 的 `02_steady` 均在约 45 分钟上限采样、`steady=no`；noPIE 在约 13 分钟满足稳定条件。此采样时刻差影响跨镜像负载可比性。noPIE 两次各 6 个 `__EXITED__` PID 没有可用 smaps/身份，保留为 `UNMEASURED`，没有假填 0 或把未知身份配给某服务；见 [process_ledger.tsv](../data/noPIE_memory_delta_reconciliation/process_ledger.tsv)。

### 表 2：三版镜像的 T/C/R（KiB）

`T` 为纳入的全部已采集用户进程；`C` 为固定 94 身份；`R` 为逐进程台账中明确不属 C 的所有已采集实例。每次直接从逐 PID 台账求和。

| 镜像 | 项目 | 启动 1 | 启动 2 | 两次均值 | 两次绝对差 |
|---|---|---:|---:|---:|---:|
| GCC | T | 572,599 | 554,891 | 563,745 | 17,708 |
| GCC | C | 515,309 | 502,846 | 509,077.5 | 12,463 |
| GCC | R | 57,290 | 52,045 | 54,667.5 | 5,245 |
| LLVM3 | T | 557,390 | 548,902 | 553,146 | 8,488 |
| LLVM3 | C | 518,574 | 511,505 | 515,039.5 | 7,069 |
| LLVM3 | R | 38,816 | 37,397 | 38,106.5 | 1,419 |
| noPIE | T | 540,855 | 539,875 | 540,365 | 980 |
| noPIE | C | 489,377 | 488,412 | 488,894.5 | 965 |
| noPIE | R | 51,478 | 51,463 | 51,470.5 | 15 |

来源：[six_snapshots.tsv](../data/noPIE_memory_delta_reconciliation/six_snapshots.tsv)、[image_summary.tsv](../data/noPIE_memory_delta_reconciliation/image_summary.tsv)。两次绝对差只表示观察到的启动间波动，不是置信区间。

### 表 3：noPIE 对两基线的均值差

| 对照 | ΔT KiB (MiB) | ΔC KiB (MiB) | ΔR KiB (MiB) | ΔT−ΔC−ΔR |
|---|---:|---:|---:|---:|
| noPIE − GCC | −23,380 (−22.832) | −20,183 (−19.710) | −3,197 (−3.122) | 0 KiB |
| noPIE − LLVM3 | −12,781 (−12.481) | −26,145 (−25.532) | +13,364 (+13.051) | 0 KiB |

每版先对两次启动等权求均值，再做镜像差；不把第 1 次启动与另一镜像第 1 次当成实验配对。来源：[comparisons.tsv](../data/noPIE_memory_delta_reconciliation/comparisons.tsv)。

### 表 4：R 的互斥类别（KiB）

类别“仅新侧实测”要求对照两次清单无该身份、noPIE 两次均有可辨身份；“双方实测未入 C”包含多实例或仅部分启动出现；只要某次未见身份且该次采集有身份不可恢复的 PID，就归“缺席未知”，其数值只代表**已采集台账**的会计贡献，不宣称未知那次真实为 0。表中实例数顺序为对照启动 1/2 → noPIE 启动 1/2。

| 对照 | 类别 | 身份数 | 实例数 | 对照均值 | noPIE 均值 | 已采集 ΔR |
|---|---|---:|---|---:|---:|---:|
| GCC | 仅新侧实测 | 4 | 0/0 → 5/5 | 0 | 16,043 | +16,043 |
| GCC | 双方实测未入 C | 3 | 5/5 → 5/5 | 31,446.5 | 32,566 | +1,119.5 |
| GCC | 缺席未知 | 8 | 7/5 → 2/1 | 23,221 | 2,861.5 | −20,359.5 |
| LLVM3 | 仅新侧实测 | 3 | 0/0 → 4/4 | 0 | 13,158 | +13,158 |
| LLVM3 | 双方实测未入 C | 4 | 6/5 → 6/6 | 35,886.5 | 35,451 | −435.5 |
| LLVM3 | 缺席未知 | 6 | 5/4 → 2/1 | 2,220 | 2,861.5 | +641.5 |

身份无法解析但**已成功测到内存**的 R 记录为 0 KiB；另有 noPIE 两次各 6 个不可读/已退出 PID，其身份与未测内存均未知，无法给未知物理内存的数值上界。原始类别表：[remaining_categories.tsv](../data/noPIE_memory_delta_reconciliation/remaining_categories.tsv)。

### 表 5：R 的主要逐身份会计贡献

以下为每个对照的全部正、负贡献（均不足 10 个），所以“其他已解析身份”余项为 **0 KiB**。四次值为对照 1/2 → noPIE 1/2 的**已测** KiB；`?` 表示至少有一次没有成功采到该身份，表内的“差”是已采集台账贡献，完整逐身份均值/差值在 [remaining_contributions.tsv](../data/noPIE_memory_delta_reconciliation/remaining_contributions.tsv) 中对此类标为 `NA`，避免把未知缺席填成 0。完整路径、实例数与匹配依据也在该表。

| 对照 | 正负 | 身份（主程序路径） | 四次已测 KiB | 已采集差 KiB | 可比性 |
|---|---|---|---|---:|---|
| LLVM3 | + | `argot` (`/usr/apps/com.samsung.tizen.argot/bin/argot`) | 0/0 → 12040/12012 | +12026 | 确认新侧两次出现 |
| LLVM3 | + | `device-policy-m` (`/usr/bin/device-policy-manager`) | 0/0 → 0/2538 | +1269 | ? |
| LLVM3 | + | `sdbd-service` (`/usr/sbin/sdbd-service`) | 0/0 → 2041/0 | +1020.5 | ? |
| LLVM3 | + | `tsr` (`/opt/usr/share/argot/.local/bin/tsr`) | 0/0 → 968/968 | +968 | 确认新侧两次出现；每次 2 实例 |
| LLVM3 | + | `storaged` (`/usr/bin/storaged`) | 1569/0 → 1562/1562 | +777.5 | 第三轮只在一次出现 |
| LLVM3 | + | `tsr-bwrap` (`/opt/usr/share/argot/.local/bin/tsr-bwrap`) | 0/0 → 164/164 | +164 | 确认新侧两次出现 |
| LLVM3 | − | `dotnet-hydra-lo` (`/usr/bin/dotnet-hydra-loader`) | 26914/27124 → 25665/26313 | −1030 | 两侧各 2 实例，负载未核实 |
| LLVM3 | − | `bash` (`/usr/bin/bash`) | 606/614 → 0/0 | −610 | ? |
| LLVM3 | − | `mediacontroller` (`/usr/bin/mediacontroller`) | 1173/1162 → 1144/0 | −595.5 | ? |
| LLVM3 | − | `gzip` (`/usr/bin/gzip`) | 403/402 → 0/0 | −402.5 | ? |
| LLVM3 | − | `bnr-service` (`/usr/apps/capi-bnr-tv/bin/bnr-service`) | 3045/3050 → 2885/2885 | −162.5 | 双方两次出现 |
| LLVM3 | − | `sleep` (`/usr/bin/sleep`) | 80/0 → 0/0 | −40 | ? |
| LLVM3 | − | `systemd` (`/usr/lib/systemd/systemd`) | 5026/5045 → 5009/5021 | −20.5 | 两侧各 2 实例，负载未核实 |
| GCC | + | `argot` (同上) | 0/0 → 12040/12012 | +12026 | 确认新侧两次出现 |
| GCC | + | `bnr-service` (同上) | 0/0 → 2885/2885 | +2885 | 确认新侧两次出现 |
| GCC | + | `dotnet-hydra-lo` (同上) | 25531/21638 → 25665/26313 | +2404.5 | 两侧各 2 实例 |
| GCC | + | `device-policy-m` (同上) | 0/0 → 0/2538 | +1269 | ? |
| GCC | + | `sdbd-service` (同上) | 0/0 → 2041/0 | +1020.5 | ? |
| GCC | + | `tsr` (同上) | 0/0 → 968/968 | +968 | 确认新侧两次出现 |
| GCC | + | `tsr-bwrap` (同上) | 0/0 → 164/164 | +164 | 确认新侧两次出现 |
| GCC | − | `perception-engine` (`/opt/usr/apps/com.samsung.tizen.perception-engine/bin/com.samsung.tizen.perception-engine`) | 16988/16881 → 0/0 | −16934.5 | ? |
| GCC | − | `acm-service` (`/usr/apps/org.tizen.acm-service/bin/acm-service`) | 4619/4620 → 0/0 | −4619.5 | ? |
| GCC | − | `systemd` (同上) | 6278/6281 → 5009/5021 | −1264.5 | 两侧各 2 实例 |
| GCC | − | `bash` (同上) | 624/632 → 0/0 | −628 | ? |
| GCC | − | `gzip` (同上) | 411/411 → 0/0 | −411 | ? |
| GCC | − | `sleep` (同上) | 92/0 → 0/0 | −46 | ? |
| GCC | − | `storaged` (同上) | 1583/1582 → 1562/1562 | −20.5 | 双方两次出现 |
| GCC | − | `mediacontroller` (同上) | 1164/0 → 1144/0 | −10 | ? |

### 表 6：旧报告值与统一重算

| 启动 | 第一部分 T | 后续报告 T | 本轮 T | 本轮−旧 T | 后续报告 C | 本轮 C | 本轮−旧 C |
|---|---:|---:|---:|---:|---:|---:|---:|
| GCC1 | 572599 | 572599 | 572599 | 0 | 515309 | 515309 | 0 |
| GCC2 | 554891 | 554891 | 554891 | 0 | 502846 | 502846 | 0 |
| LLVM3-1 | 557390 | 557390 | 557390 | 0 | 518574 | 518574 | 0 |
| LLVM3-2 | 548902 | 548902 | 548902 | 0 | 511505 | 511505 | 0 |
| noPIE1 | 540855 | 540855 | 540855 | 0 | 489377 | 489377 | 0 |
| noPIE2 | 539875 | 539875 | 539875 | 0 | 488412 | 488412 | 0 |

来源：[historical_value_check.tsv](../data/noPIE_memory_delta_reconciliation/historical_value_check.tsv)。旧报告与本轮**数值无需更正**；应补充两条表述边界：其一，“全部用户进程”是“已采集的用户进程”，noPIE 每次有 6 个退出/未完整采到的 PID；其二，94 身份与总量改善幅度不同主要因 R 中的进程集合/运行状态变化，不能把 −26,145 KiB 解释成全系统的编译器或预链接收益。旧 [noPIE_followup_validation.md](noPIE_followup_validation.md) 的 94 身份值准确，本报告是其 R 的详细账本。

## 守恒、不能解释的部分与复现

六次 `T=C+R`、两组 `ΔT=ΔC+ΔR`、R 的互斥类别之和与逐身份之和均**精确为 0 KiB 误差**，没有容差；见 [validation.json](../data/noPIE_memory_delta_reconciliation/validation.json)。实测 R 的身份未解析贡献为 **0 KiB**；但 noPIE 每次 6 个退出 PID 的身份及未测内存未知，不能定量补入。涉及这类缺口的逐身份真实差值为 `NA`；其在已采集 R 台账中的净额为 LLVM3 对照 +641.5 KiB、GCC 对照 −20,359.5 KiB。后一数额主要是 GCC 实测而 noPIE 未采到的 `perception-engine` 与 `acm-service`，不能把“未采到”当成全部运行时间的服务缺席。PSS 随共享者数量变化，以上分解只是会计归属，不是可独立回收的物理内存或单一构建选项的因果效果。noPIE 同时含 noPIE、LTO、MLGO 等变化。

复现命令（仓库根目录；只读原始输入）：

```bash
ulimit -v 2500000
taskset -c 0 nice -n 19 python3 -m unittest memdiff/tests/test_nopie_memory_delta_reconciliation.py
taskset -c 0 nice -n 19 ionice -c3 python3 memdiff/scripts/nopie_memory_delta_reconciliation.py --manifest memdiff/data/noPIE_memory_delta_reconciliation/input_manifest.json --out memdiff/data/noPIE_memory_delta_reconciliation
```

小样本测试 **5/5 通过**（缺 SwapPss、多实例与同名异路径、确认缺席和采集未知、仅一次出现的均值、重复 PID 和守恒错误检测）；本次运行命令、退出码与进度见 `data/noPIE_memory_delta_reconciliation/run_console.log`、`unit_tests.log`。本轮没有重写历史原始文件。
