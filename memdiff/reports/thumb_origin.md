# 11-11 LLVM 镜像 ARM 模式文件来源与 Thumb-2 体积参照

输入为 `memdiff/data/extra_levers_sizing/thumb_coverage.tsv`、`memdiff/data/llvm_memory_budget/` 以及 `memdiff/data/system_code_page_sections/elf/`（2026-11-11，`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`）。本轮完全离线，没有连接开发板，也没有重编文件。分析脚本与逐文件证据在 `memdiff/data/thumb_origin/`；`progress.log`、`console.log` 保存进度和结束状态。主机执行固定 CPU0/nice19/ionice idle、Python 虚拟内存上限 2,500,000 KiB。ELF 工具均为第三轮 GBS root 的交叉 readelf/objdump，Binutils 2.43；objdump 所需 `libopcodes` 从同一 GBS root `usr/lib64` 加载，没有使用主机工具链。

## 范围与方法

按 `.dynsym` **已定义 FUNC** 地址最低位的既有统计，ARM 占比 >80% 的 **106** 个文件，以及 ARM 占比 20%–80% 的 **12** 个文件单列，共 118 个。原始 `.comment` 全部字符串、`.ARM.attributes` 全部标签、节表、程序头和动态符号 readelf 输出保存在 `readelf_raw.jsonl.gz`；每个目标文件的内容和路径类别在 `file_properties.tsv`。其中 `.comment` 标记只有 GCC 的 33 个，同时有 GCC 与 clang 字符串的 85 个，没有纯 clang 标记或完全无标记的文件。混合标记不能证明某个源码包由 clang 完整编译。

`.text` 按 4 KiB 文件页均匀选最多 64 个不同页，每页读 256 字节；小于 64 页的文件按实际页数。每段用交叉 objdump 的原始二进制 ARM 模式和 `force-thumb` 模式各解码一次。`sample_disassembly.tsv` 留存文件偏移、两种模式可识别指令字节比例、附近已定义动态 FUNC 符号的模式和决策依据。若动态符号覆盖样本至少 128 字节且某模式覆盖量至少为另一模式两倍，优先取符号模式；否则两种合法字节比例差至少 15 个百分点时取较高者；仍无法判定的样本用该文件 `.dynsym` 函数 ARM 比例填补整段估计。共 **3,130 个不同页样本，1,450 个（46.3%）未能由局部证据区分模式**，故 `ARM_text_fraction_estimate` 是粗略估计，绝非整段精确反汇编。`.ARM.attributes` 声明 Thumb-2 可用不等于代码实际为 Thumb。

NEON/VFP 向量特征只计样本中 `vld1–vld4`、`vst1–vst4`、带整数/多项式类型的向量指令或显式 `qN` 寄存器；普通 VFP 标量指令不计。符号名的 `_neon`、`_armv6`、`_asm` 单列在 `file_properties.tsv`。分类为“汇编/向量特征较多”须至少 8 个已判模式的样本、至少 3 个向量样本且比例≥10%，或至少 5 个上述特征符号名。这只是筛选规则，不能证明源码使用手写汇编或确实属于性能热点。

路径类别按 `/prd`、`/opt/usr/apps`、`/usr/local`、`/hal`、`/usr/lib`、`/usr/bin`、其他分别记录。`file_properties.tsv` 同时给出 `.text`、`.rodata`、可执行 LOAD 文件大小、唯一 r-x 驻留、该文件所有映射 Pss、r-x 各节折算 Pss、r--/rw- Private_Dirty、映射进程数以及同名 Thumb 副本路径。Pss 来自 `llvm_memory_budget/vmas_all.tsv`、`code_file_pss.tsv`；唯一驻留来自 `system_code_page_sections/files_from_pages.tsv`。`Private_Dirty` 没有与 Pss 相加。

## 同名 ARM / Thumb 文件的实测大小

在已拉回、且同时被映射的 ELF 中，以相同 SONAME 或文件名寻找 ARM 占比 >80% 对 Thumb 占比 <20% 的副本，只找到 **2 对**，都属于 `libtvs-api.so`。比值为 Thumb 版除 ARM 版；完整数据及双方 readelf 原文见 `arm_thumb_pairs.tsv`、`pair_readelf_raw.jsonl.gz`。

| ARM 文件 | Thumb 文件 | `.text` 比值 | `.rodata` 比值 | 可执行 LOAD 比值 | 已定义动态 FUNC（ARM/Thumb） |
|---|---|---:|---:|---:|---:|
| `/opt/usr/apps/com.samsung.tv.slive-daemon/lib/libtvs-api.so` | `/usr/lib/libtvs-api.so` | 0.677745 | 1.000394 | 0.950268 | 3,269 / 4,692 |
| `/opt/usr/apps/org.tizen.dseal/lib/libtvs-api.so` | `/usr/lib/libtvs-api.so` | 0.687952 | 1.210183 | 0.956881 | 3,447 / 4,692 |

`.text` 比值中位数 **0.682849**，范围 **0.677745–0.687952**。样本只有 2 对；两对导出函数数均不同，说明内容或版本不一致，**没有可归因于单独切换 Thumb-2 的同版本实测比值**。下节仅按这两个跨版本比值作参考算术推算，不把差异归因于 Thumb。

## 来源归类与条件性推算

互斥归类顺序：先看较多汇编/向量特征；其次把 `/prd`、`/opt/usr/apps`、`/usr/local`、`/hal` 的文件列为应用/厂商路径；剩余文件按 `.comment` 的纯 GCC、纯 clang，或无法判断归类。应用/厂商路径只说明**提供的数据中没有源码与重编路径**，不能证明客观上无法重编。`.comment` 也可能混合来自启动文件或不同编译单元，纯 GCC 标记并非完整构建链证明。证据为 `file_properties.tsv` 和 `class_summary.tsv`。

| 类别 | 文件数 | `.text` KiB | 唯一 r-x 驻留 KiB | 文件映射 Pss KiB |
|---|---:|---:|---:|---:|
| 应用/厂商路径，源码可得性未确定 | 15 | 16,297.367 | 9,068 | 9,440 |
| 仅见 GCC `.comment` 标记 | 23 | 13,732.465 | 8,396 | 12,307 |
| 仅见 clang 标记的 ARM 文件 | 0 | 0 | 0 | 0 |
| 汇编/向量特征较多 | 16 | 20,673.238 | 9,276 | 11,691 |
| 无法判断 | 64 | 6,261.447 | 4,872 | 6,419 |

用两对 `.text` 比值中位数 0.682849 按比例套到“仅见 GCC”类别，算术上 `.text` 减少 **4,355.272 KiB**、唯一 r-x 驻留减少 **2,662.804 KiB**；“仅见 clang”类别为 **0/0 KiB**。公式为当前类别量×(1−比值)，逐类见 `ratio_estimates.tsv`。这是**样本不足且配对版本不一致的参考推算**，不是可得收益，也不能证明这些文件可以直接用 `-mthumb` 安全重编。若需判断实际收益，必须在同一源码版本、相同优化与链接选项下分别构建 ARM/Thumb 两份并测性能、ABI/汇编兼容及驻留。

供内网核查包和 spec 的完整路径表为 `data/thumb_origin/to_check_paths.txt`，仅收“仅见 GCC”与“仅见 clang”两类，按文件映射 Pss 降序。前 10 个：

1. `/usr/apps/com.samsung.tizen.argot/bin/argot`
2. `/usr/lib/ld-linux.so.3`
3. `/usr/bin/bt-service`
4. `/usr/bin/deviced`
5. `/usr/lib/libdeviced.so.1.0.3`
6. `/usr/lib/libnss_compat.so.2`
7. `/usr/lib/libpthread.so.0`
8. `/usr/lib/libbluetooth-api.so.1.0.0`
9. `/usr/apps/org.tizen.webserver/bin/liblighttpd.so`
10. `/usr/lib/librt.so.1`

这些是**核查候选，不是改动建议**。尤其 `ld-linux.so.3`、libc 相关运行时与性能敏感服务要单独核对源、ABI、启动行为和性能。完整中间表与 `qa.json` 可复核 106+12 范围、五类求和、样本数与配对数。
