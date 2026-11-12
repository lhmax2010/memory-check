# VD LLVM：保留 PIE、无预链接时的内存预算与静态优化上限

采集基准：2026-11-11 LLVM 板，`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`。本报告只分析该 LLVM 镜像；第三轮 LLVM 的两次开机只作量级参照，不用 GCC 数字或跨镜像差值推断收益。该批 1,452 个 ELF 的预链接标记数为 0（原始 `elf_summary.tsv`）；本次静态表中 PIE 标记可执行文件 103 个。数据来自 [`system_code_page_sections`](../data/system_code_page_sections/) 的 `collection.json`、每进程 `raw/process_*.stdout`、`section_residency.tsv`、`unique_pages.tsv.gz`、`elf_summary.tsv` 和原样拉回 ELF；逐项计算表与脚本在 [`llvm_memory_budget`](../data/llvm_memory_budget/)。开发机 CPU0/nice19/ionice3 串行，Python 2.5 GB 虚拟内存上限，`progress.log` 与各阶段日志记录执行。

## 一、同次快照 Pss 预算

原始采集列出 322 个 PID，其中 316 个完整；这 316 个里 **111 个有用户态 VMA**，其余为无用户映射的内核线程，另有 6 个退出或记录不完整。因此以下总量是 111 个可读进程的同次快照，不声称覆盖退出的进程。Pss=563,596 KiB，SwapPss=96,976 KiB，Pss+SwapPss=660,572 KiB。来源：[`smaps_budget.json`](../data/llvm_memory_budget/smaps_budget.json)、[`process_distribution.tsv`](../data/llvm_memory_budget/process_distribution.tsv)、[`vmas_all.tsv`](../data/llvm_memory_budget/vmas_all.tsv)。

| 互斥类别 | Pss KiB | 占总 Pss |
|---|---:|---:|
| r-x 加载器相关节 | 63,790.9 | 11.32% |
| r-x .text | 112,626.2 | 19.98% |
| r-x .rodata | 26,086.3 | 4.63% |
| r-x .ARM.exidx/.ARM.extab | 1,232.7 | 0.22% |
| r-x .plt | 4,329.1 | 0.77% |
| r-x 其余 | 4,853.8 | 0.86% |
| 文件 r-- 私有脏 | 103,420 | 18.35% |
| 文件 r-- 共享脏 Pss | 1,898 | 0.34% |
| 文件 r-- 干净 Pss | 19,679 | 3.49% |
| 文件 rw- 私有脏 | 30,280 | 5.37% |
| 文件 rw- 共享脏 Pss | 565 | 0.10% |
| 文件 rw- 干净 Pss | 8,676 | 1.54% |
| [heap] | 77,846 | 13.81% |
| 无名匿名映射 | 84,809 | 15.05% |
| [stack] / [stack:tid] | 2,516 | 0.45% |
| 其余带名匿名映射 | 20,968 | 3.72% |
| 其余文件映射 | 20 | 0.00% |
| **合计** | **563,596** | **100.00%** |

SwapPss 另计 96,976 KiB，占 Pss+SwapPss 的 14.68%；它不是 Pss 的子类，未加入上表分母。文件映射私有脏页用 `Private_Dirty`；共享脏页 Pss 用 `Pss_Dirty−Private_Dirty`；干净页用 `Pss−Pss_Dirty`。所有 VMA 的 `Private_Dirty≤Pss`，上表合计经脚本核对精确等于总 Pss。r-x 节分类按文件唯一 present 页的节占比折算到同文件逐映射 Pss，跨节页按字节比例分摊；无法归到 ELF 节的 r-x Pss 进入“其余”。来源：[`code_file_pss.tsv`](../data/llvm_memory_budget/code_file_pss.tsv)、[`code_budget.json`](../data/llvm_memory_budget/code_budget.json)、[`compute.py`](../data/llvm_memory_budget/compute.py)。

VMA 数（111 个有 VMA 进程）中位数 460、90 分位 1,050、最大 2,729；映射 `.so` 去重数分别为 128、283、476。逐进程值见 `process_distribution.tsv`。

11-11 的 `system_code_page_sections` 采集未保存同次 `/proc/meminfo`：**PageTables 同次值未找到**。仅作量级参照，第三轮 LLVM 两次 `02_steady/meminfo.txt` 第 33 行分别是 16,164 和 16,052 KiB；其第三轮用户态 Pss 为 436,407/427,746 KiB。不同 BUILD_ID、开机日期和进程集合，不与本次预算相减作结论。来源：[`llvm_round3/boot1`](../data/llvm_round3/boot1/memcheck/llvm_boot1_20261103_015124/02_steady/meminfo.txt)、[`boot2`](../data/llvm_round3/boot2/memcheck/llvm_boot2_20261103_030258/02_steady/meminfo.txt) 及各自 `totals.txt`。

## 二、重定位目标页和文件私脏

交叉 readelf 对 1,452 个已映射 ARM ELF 的动态重定位解析无错误，共 1,755,115 条。按类型：RELATIVE 1,044,786、ABS32 270,865、GLOB_DAT 65,622、JUMP_SLOT 372,944、其他 898。逐条目标虚拟地址、节、文件页及符号在 [`relocation_targets.tsv.gz`](../data/llvm_memory_budget/relocation_targets.tsv.gz)，逐页在 [`relocation_pages.tsv`](../data/llvm_memory_budget/relocation_pages.tsv)，逐文件误差在 [`relocation_model_by_file.tsv`](../data/llvm_memory_budget/relocation_model_by_file.tsv)。

对文件可写节的目标页去重，再乘同快照映射该库的进程数：所有动态重定位页静态预测 **183,612 KiB**；排除未设 NOW 且只含 JUMP_SLOT 的页后为 **181,356 KiB**。同批库 `r--+rw-` 文件映射实测 Private_Dirty **128,184 KiB**。全量预测高 55,428 KiB，逐库绝对误差和占实测 44.0%；排除延迟绑定专属页后仍高 53,172 KiB。**误差超过 20%，模型不适合充当可得收益预测**：静态目标不等于实际写脏、进程映射时间不完全同步、运行时自身写页及被跳过的重定位路径都可能影响，现有离线证据不能逐项定因。

| 静态页标签（每进程×库，允许重叠） | KiB | 占静态预测 |
|---|---:|---:|
| 含已识别 _ZTV 目标的页 | 22,680 | 12.35% |
| 含已识别 _ZTI 目标的页 | 23,644 | 12.88% |
| 以上两类同页交集 | 22,204 | 12.09% |
| 目标字节合计 <256 B 的页 | 65,348 | 35.59% |
| 目标位于 .data.rel.ro 的页 | 45,824 | 24.96% |

`.data.rel.ro` 目标对象按 `.dynsym` 定义区间、目标函数符号，以及 ARM REL 原位加数指向 `.text/.plt` 或可打印的 NUL 结尾 `.rodata` 作保守分类。后两项只是候选，无法由字节内容证明源代码表用途；详细目标及规则见 [`relro_target_classification.tsv.gz`](../data/llvm_memory_budget/relro_target_classification.tsv.gz)、[`relro_classification_summary.json`](../data/llvm_memory_budget/relro_classification_summary.json)。下表目标数包含主程序与库，页上界按映射进程加权；各类同页重叠，不能与上面的库专属页表直接相加。

| `.data.rel.ro` 目标类 | 重定位目标数 | 含该类的每进程×ELF 页上界 KiB |
|---|---:|---:|
| _ZTV 虚表 | 175,720 | 22,944 |
| _ZTI typeinfo | 60,213 | 23,932 |
| 其他函数指针候选 | 536,893 | 55,288 |
| 字符串指针候选 | 262,580 | 79,244 |
| 无法归类 | 149,258 | 62,356 |

上述 _ZTV/_ZTI 是 `.dynsym` 中**定义的 OBJECT 符号地址区间覆盖重定位目标**时的页标签，不是能节省的脏页数。两类大量同页，不能相加；含未知目标容器的页累计 182,284 KiB（该统计与其他标签重叠），因为去除了 `.symtab` 的本地表难以归类。“其他函数/字符串指针表”现有符号证据**未确定**。仅完全由已识别虚表容器覆盖的页为 20 KiB，也不能保证改 ABI 后无运行时其他写入。<256 B 页数与字节分布见 `relocation_pages.tsv` 的 `target_count/byte_fraction`；不把整页占用等同于优化收益。

静态模型中每库 1–2 个可写目标页的小库有 1,145 个，按其映射进程数累加 104,760 KiB；前 50 与**同一快照 PID 集合完全相同**的共加载组见 [`small_library_top50.tsv`](../data/llvm_memory_budget/small_library_top50.tsv)、[`small_library_comapping_groups.tsv`](../data/llvm_memory_budget/small_library_comapping_groups.tsv)。这只是文件页预测，不能证明合库后能收回同量。

## 三、动态符号与绑定

逐 ELF 的 GLOBAL/WEAK 已定义与未定义个数、`.dynsym/.dynstr/.gnu.hash/.hash/.rel.dyn/.rel.plt` 字节数、DT_FLAGS/DT_FLAGS_1、PIE、DT_NEEDED 在 [`elf_metrics.tsv`](../data/llvm_memory_budget/elf_metrics.tsv)。1,452 个映射 ELF 中，NOW/BIND_NOW **92** 个，未设全绑定 **1,360** 个；各有 JUMP_SLOT 的分别为 91/1,360。这里“未设全绑定”只表示允许延迟绑定，不证明实际何时解析。加载器相关节驻留前 50 见 [`loader_residency_top50.tsv`](../data/llvm_memory_budget/loader_residency_top50.tsv)。

LLVM 本身已定义 WEAK 导出共 198,643：按互斥名称类分，模板名候选 126,180、其他类成员函数 26,746、vtable/typeinfo 35,309、其他 10,408。用于可见性估算的‘类成员函数候选’跨上述模板类与其他类成员类，只按反解名含 `::` 和 `(` 取数。这是对 LLVM 全部符号的独立分类，不依赖 GCC。逐符号见 [`weak_symbols_classified.tsv.gz`](../data/llvm_memory_budget/weak_symbols_classified.tsv.gz) 和 [`weak_category_by_file.tsv`](../data/llvm_memory_budget/weak_category_by_file.tsv)。`c++filt` 名字不能证明函数真的 inline。

三项静态估算：① `-fvisibility-inlines-hidden` 仅取 161,913 个未核实类成员候选，按每个 16 B dynsym + 2 B version + 4 B hash + 名字长度加 NUL，直接表项结构字节合计上限 **21,693.5 KiB**，不是可收回 Pss；② `-Bsymbolic-functions` 的“本库 `.dynsym` 已定义 FUNC 且目标为 JUMP_SLOT/GLOB_DAT”候选 **200,066 条**（JUMP_SLOT 182,149，GLOB_DAT 17,917），转成本地绑定不自动让页变干净；③ `--as-needed` 能移除的映射数 **未确定**，当前被映射 ELF 有 15,720 条 NEEDED 边，但静态符号匹配不能确认构造函数、`dlopen`、弱引用和实际提供者，需链接 map/重链实验与运行时加载清单。来源：[`symbol_estimates.json`](../data/llvm_memory_budget/symbol_estimates.json)、`relocation_targets.tsv.gz`。

## 四、代码页热度参考

唯一 r-x 驻留前 50 文件的 `.text` 大小、驻留页数、连续段数、最长连续段及平均页间隔见 [`code_top50_pages.tsv`](../data/llvm_memory_budget/code_top50_pages.tsv)。驻留比例为驻留 `.text` 页数×4 KiB / `.text` 静态大小；跨节页计入该节的重叠页，故这是页级比例。
这 50 个文件共 15,305 个 `.text` 驻留页。若**假设**每页只有 25% 热字节且能完全重排，按逐文件向上取整最少 3,844 页；若假设 50%，最少 7,665 页。对应的 45,844/30,560 KiB 只是热字节比例假设下的紧凑排布数学差额，未测量指令热度、函数边界或实际可得收益。

## 五、优化手段与作用上限（不排序）

下表“当前 KiB”是可作用的预算池，不是该手段的收益；“未确定”表示现有单镜像静态数据无法给可得收益。所有上限都须经过同镜像只改一项的构建与运行验证。

| 手段 | 预算类别与当前 KiB | 本次可算上限或估计 | 前提 | 主要风险 |
|---|---:|---|---|---|
| LTO | .text 112,626.2 | 可得 Pss 未确定；理论上不超过整类 .text Pss | GNU ld/工程与构建链验证 | 构建时间、代码布局及性能变化 |
| -fvisibility-inlines-hidden | 加载器节 63,790.9 | 161,913 个候选；直接符号表结构 ≤21,693.5 KiB，Pss 未确定 | GNU ld + C++ 工程 | ABI / dlsym 依赖、inline 判定不充分 |
| 按包改 -fvisibility=hidden | 加载器节 63,790.9 | 可隐藏符号与 Pss 未确定 | 改工程导出列表 | ABI、插件与符号可见性 |
| --exclude-libs | 加载器节 63,790.9 | 可隐藏静态库导出与 Pss 未确定 | GNU ld；识别归档包 | ABI、动态查找 |
| -Bsymbolic-functions | 文件私有脏 133,700 | 本库函数目标候选 200,066 条；脏页收益未确定 | GNU ld | 符号插桩/覆盖语义 |
| 延迟绑定 | 文件私有脏 133,700 | NOW 库仅 JUMP_SLOT 的页 ≤72 KiB；运行后收益未确定 | GNU ld 与安全策略允许 | 首次调用延迟、RELRO/安全要求 |
| --as-needed | 文件映射 Pss 377,457 | 可删除映射数未确定；当前 NEEDED 边 15,720 | GNU ld / 重链 | 构造函数副作用、隐式依赖 |
| RELR（仅 lld） | r-x .rel.dyn 6,556.1 | 该类 Pss 理论上限 6,556.1；可得未确定 | lld 与加载器支持 RELR | 兼容性、加载器升级 |
| 合并小库 | 文件私有脏 133,700 | 静态 1–2 页小库模型 104,760 KiB，但模型误差 >20%，可得未确定 | 改工程/库边界 | ABI、装载及升级粒度 |
| C++ 相对虚表 | 文件私有脏 133,700 | 含 _ZTV 页 22,680 KiB，上界与 typeinfo/未知目标重叠；可得未确定 | 改 C++ ABI/工具链 | ABI 与虚派发兼容性 |
| 按热度排布函数 | .text 112,626.2 | 前 50 的 25%/50% 热字节假设为 45,844/30,560 KiB；非实测收益 | 需要剖析与链接排序 | 工作负载偏差、I-cache 性能 |
| ICF（仅 lld） | .text 112,626.2 | 相同函数可折叠量未确定 | lld / 工程 | 地址身份语义、调试 |
| Machine Outliner | .text 112,626.2 | 可提取代码量未确定 | LLVM 编译选项/工程 | 性能、调试及代码布局 |
| 减少 LOAD 段 | PageTables 同次值未找到；VMA 中位数 460 | 页表/VMA 收益未确定 | 链接脚本或工程 | 内存保护边界、兼容性 |

### 证据边界

单次采集内的动态符号页模型高估实测 43.96%；各方法的“页上界”不能相加，也不能与 Pss 池直接相减。PageTables 同次数据、`.symtab` 已去除对象的本地表类型、真实热字节、未引用 NEEDED 的可安全删除性均未找到或未确定。需要按包重编与同镜像复测才能得到可得收益；本任务没有修改构建配置，也没有在板上执行。

脚本执行顺序：`compute.py`（完整 ELF 和 smaps）、`weak_symbols.py`、`classify_relro.py`、`derive.py`、`build_report.py`。日志中保留首次校验失败和修正后的成功运行；最终数据以各脚本最后一次 `状态=成功` 为准。
