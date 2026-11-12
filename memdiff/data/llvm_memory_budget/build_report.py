#!/usr/bin/env python3
"""Render the LLVM-only memory budget from generated tables and QA checks."""
import csv,datetime,json,math
from pathlib import Path

O=Path(__file__).resolve().parent
M=O.parents[1]
R=M/'reports/llvm_memory_budget.md'
def load(name):return json.loads((O/name).read_text())
def rows(name):
 with (O/name).open() as f:return list(csv.DictReader(f,delimiter='\t'))
def fmt(n):return f'{n:,.1f}' if isinstance(n,float) and not n.is_integer() else f'{n:,.0f}'
def main():
 d=load('derived_summary.json');rel=load('relocation_summary.json');sym=load('symbol_estimates.json')
 relro=load('relro_classification_summary.json')
 pie_count=sum(int(r['PIE']) for r in rows('elf_metrics.tsv'))
 b=d['budget_Pss_kB'];total=d['Pss_total_kB'];p=d['relocation_page_bounds'];c=d['section_Pss_kB']
 budget_order=[('code_loader_related','r-x 加载器相关节'),('code_text','r-x .text'),
 ('code_rodata','r-x .rodata'),('code_arm_unwind','r-x .ARM.exidx/.ARM.extab'),
 ('code_plt','r-x .plt'),('code_code_other','r-x 其余'),
 ('file_r--_private_dirty','文件 r-- 私有脏'),('file_r--_shared_dirty_Pss','文件 r-- 共享脏 Pss'),
 ('file_r--_clean','文件 r-- 干净 Pss'),('file_rw-_private_dirty','文件 rw- 私有脏'),
 ('file_rw-_shared_dirty_Pss','文件 rw- 共享脏 Pss'),('file_rw-_clean','文件 rw- 干净 Pss'),
 ('anon_heap','[heap]'),('anon_unlabelled','无名匿名映射'),('anon_stack','[stack] / [stack:tid]'),
 ('anon_other_named','其余带名匿名映射'),('file_other','其余文件映射')]
 lines=['# VD LLVM：保留 PIE、无预链接时的内存预算与静态优化上限','',
 f'采集基准：2026-11-11 LLVM 板，`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`。本报告只分析该 LLVM 镜像；第三轮 LLVM 的两次开机只作量级参照，不用 GCC 数字或跨镜像差值推断收益。该批 1,452 个 ELF 的预链接标记数为 0（原始 `elf_summary.tsv`）；本次静态表中 PIE 标记可执行文件 {pie_count} 个。数据来自 [`system_code_page_sections`](../data/system_code_page_sections/) 的 `collection.json`、每进程 `raw/process_*.stdout`、`section_residency.tsv`、`unique_pages.tsv.gz`、`elf_summary.tsv` 和原样拉回 ELF；逐项计算表与脚本在 [`llvm_memory_budget`](../data/llvm_memory_budget/)。开发机 CPU0/nice19/ionice3 串行，Python 2.5 GB 虚拟内存上限，`progress.log` 与各阶段日志记录执行。',
 '', '## 一、同次快照 Pss 预算','',
 f"原始采集列出 322 个 PID，其中 316 个完整；这 316 个里 **111 个有用户态 VMA**，其余为无用户映射的内核线程，另有 6 个退出或记录不完整。因此以下总量是 111 个可读进程的同次快照，不声称覆盖退出的进程。Pss={fmt(total)} KiB，SwapPss={fmt(d['SwapPss_total_kB'])} KiB，Pss+SwapPss={fmt(d['Pss_plus_SwapPss_kB'])} KiB。来源：[`smaps_budget.json`](../data/llvm_memory_budget/smaps_budget.json)、[`process_distribution.tsv`](../data/llvm_memory_budget/process_distribution.tsv)、[`vmas_all.tsv`](../data/llvm_memory_budget/vmas_all.tsv)。",
 '', '| 互斥类别 | Pss KiB | 占总 Pss |','|---|---:|---:|']
 for key,label in budget_order:lines.append(f'| {label} | {fmt(float(b[key]))} | {float(b[key])/total*100:.2f}% |')
 lines.extend([f'| **合计** | **{fmt(total)}** | **100.00%** |','',
 f"SwapPss 另计 {fmt(d['SwapPss_total_kB'])} KiB，占 Pss+SwapPss 的 {d['SwapPss_total_kB']/d['Pss_plus_SwapPss_kB']*100:.2f}%；它不是 Pss 的子类，未加入上表分母。文件映射私有脏页用 `Private_Dirty`；共享脏页 Pss 用 `Pss_Dirty−Private_Dirty`；干净页用 `Pss−Pss_Dirty`。所有 VMA 的 `Private_Dirty≤Pss`，上表合计经脚本核对精确等于总 Pss。r-x 节分类按文件唯一 present 页的节占比折算到同文件逐映射 Pss，跨节页按字节比例分摊；无法归到 ELF 节的 r-x Pss 进入“其余”。来源：[`code_file_pss.tsv`](../data/llvm_memory_budget/code_file_pss.tsv)、[`code_budget.json`](../data/llvm_memory_budget/code_budget.json)、[`compute.py`](../data/llvm_memory_budget/compute.py)。",
 '', f"VMA 数（111 个有 VMA 进程）中位数 {fmt(d['VMA_distribution']['median'])}、90 分位 {fmt(d['VMA_distribution']['p90'])}、最大 {fmt(d['VMA_distribution']['max'])}；映射 `.so` 去重数分别为 {fmt(d['mapped_libraries_distribution']['median'])}、{fmt(d['mapped_libraries_distribution']['p90'])}、{fmt(d['mapped_libraries_distribution']['max'])}。逐进程值见 `process_distribution.tsv`。",
 '', '11-11 的 `system_code_page_sections` 采集未保存同次 `/proc/meminfo`：**PageTables 同次值未找到**。仅作量级参照，第三轮 LLVM 两次 `02_steady/meminfo.txt` 第 33 行分别是 16,164 和 16,052 KiB；其第三轮用户态 Pss 为 436,407/427,746 KiB。不同 BUILD_ID、开机日期和进程集合，不与本次预算相减作结论。来源：[`llvm_round3/boot1`](../data/llvm_round3/boot1/memcheck/llvm_boot1_20261103_015124/02_steady/meminfo.txt)、[`boot2`](../data/llvm_round3/boot2/memcheck/llvm_boot2_20261103_030258/02_steady/meminfo.txt) 及各自 `totals.txt`。',
 '', '## 二、重定位目标页和文件私脏','',
 f"交叉 readelf 对 1,452 个已映射 ARM ELF 的动态重定位解析无错误，共 {fmt(rel['dynamic_relocations_parsed'])} 条。按类型：RELATIVE {fmt(rel['total_relocation_types']['RELATIVE'])}、ABS32 {fmt(rel['total_relocation_types']['ABS32'])}、GLOB_DAT {fmt(rel['total_relocation_types']['GLOB_DAT'])}、JUMP_SLOT {fmt(rel['total_relocation_types']['JUMP_SLOT'])}、其他 {fmt(rel['total_relocation_types']['other'])}。逐条目标虚拟地址、节、文件页及符号在 [`relocation_targets.tsv.gz`](../data/llvm_memory_budget/relocation_targets.tsv.gz)，逐页在 [`relocation_pages.tsv`](../data/llvm_memory_budget/relocation_pages.tsv)，逐文件误差在 [`relocation_model_by_file.tsv`](../data/llvm_memory_budget/relocation_model_by_file.tsv)。",
 '', f"对文件可写节的目标页去重，再乘同快照映射该库的进程数：所有动态重定位页静态预测 **{fmt(rel['library_prediction_kB'])} KiB**；排除未设 NOW 且只含 JUMP_SLOT 的页后为 **{fmt(rel['library_eager_or_nonplt_prediction_kB'])} KiB**。同批库 `r--+rw-` 文件映射实测 Private_Dirty **{fmt(rel['library_observed_file_r--_rw-_Private_Dirty_kB'])} KiB**。全量预测高 {fmt(rel['signed_error_kB'])} KiB，逐库绝对误差和占实测 {rel['absolute_percentage_error_vs_observed']*100:.1f}%；排除延迟绑定专属页后仍高 {fmt(rel['library_eager_or_nonplt_prediction_kB']-rel['library_observed_file_r--_rw-_Private_Dirty_kB'])} KiB。**误差超过 20%，模型不适合充当可得收益预测**：静态目标不等于实际写脏、进程映射时间不完全同步、运行时自身写页及被跳过的重定位路径都可能影响，现有离线证据不能逐项定因。",
 '', '| 静态页标签（每进程×库，允许重叠） | KiB | 占静态预测 |','|---|---:|---:|'])
 for key,label in [('vtable_upper_kB','含已识别 _ZTV 目标的页'),('typeinfo_upper_kB','含已识别 _ZTI 目标的页'),
                   ('both_vtable_typeinfo_kB','以上两类同页交集'),('lt256_target_bytes_kB','目标字节合计 <256 B 的页'),
                   ('data_rel_ro_page_kB','目标位于 .data.rel.ro 的页')]:
  lines.append(f"| {label} | {fmt(p[key])} | {p[key]/rel['library_prediction_kB']*100:.2f}% |")
 lines.extend(['','`.data.rel.ro` 目标对象按 `.dynsym` 定义区间、目标函数符号，以及 ARM REL 原位加数指向 `.text/.plt` 或可打印的 NUL 结尾 `.rodata` 作保守分类。后两项只是候选，无法由字节内容证明源代码表用途；详细目标及规则见 [`relro_target_classification.tsv.gz`](../data/llvm_memory_budget/relro_target_classification.tsv.gz)、[`relro_classification_summary.json`](../data/llvm_memory_budget/relro_classification_summary.json)。下表目标数包含主程序与库，页上界按映射进程加权；各类同页重叠，不能与上面的库专属页表直接相加。','','| `.data.rel.ro` 目标类 | 重定位目标数 | 含该类的每进程×ELF 页上界 KiB |','|---|---:|---:|'])
 for key,label in [('vtable','_ZTV 虚表'),('typeinfo','_ZTI typeinfo'),('other_function_pointer_candidate','其他函数指针候选'),('string_pointer_candidate','字符串指针候选'),('unknown','无法归类')]:
  lines.append(f"| {label} | {fmt(relro['target_class_counts'].get(key,0))} | {fmt(relro['weighted_page_upper_kB_by_class'].get(key,0))} |")
 lines.extend(['',
 f"上述 _ZTV/_ZTI 是 `.dynsym` 中**定义的 OBJECT 符号地址区间覆盖重定位目标**时的页标签，不是能节省的脏页数。两类大量同页，不能相加；含未知目标容器的页累计 {fmt(p['unknown_container_page_kB'])} KiB（该统计与其他标签重叠），因为去除了 `.symtab` 的本地表难以归类。“其他函数/字符串指针表”现有符号证据**未确定**。仅完全由已识别虚表容器覆盖的页为 {fmt(p.get('only_vtable_container_kB',0))} KiB，也不能保证改 ABI 后无运行时其他写入。<256 B 页数与字节分布见 `relocation_pages.tsv` 的 `target_count/byte_fraction`；不把整页占用等同于优化收益。",
 '', f"静态模型中每库 1–2 个可写目标页的小库有 {fmt(p['small_library_1to2_files'])} 个，按其映射进程数累加 {fmt(p['small_library_1to2_page_kB'])} KiB；前 50 与**同一快照 PID 集合完全相同**的共加载组见 [`small_library_top50.tsv`](../data/llvm_memory_budget/small_library_top50.tsv)、[`small_library_comapping_groups.tsv`](../data/llvm_memory_budget/small_library_comapping_groups.tsv)。这只是文件页预测，不能证明合库后能收回同量。",
 '', '## 三、动态符号与绑定','',
 f"逐 ELF 的 GLOBAL/WEAK 已定义与未定义个数、`.dynsym/.dynstr/.gnu.hash/.hash/.rel.dyn/.rel.plt` 字节数、DT_FLAGS/DT_FLAGS_1、PIE、DT_NEEDED 在 [`elf_metrics.tsv`](../data/llvm_memory_budget/elf_metrics.tsv)。1,452 个映射 ELF 中，NOW/BIND_NOW **{fmt(d['BIND_NOW_mapped_ELF'].get('NOW',0))}** 个，未设全绑定 **{fmt(d['BIND_NOW_mapped_ELF'].get('lazy_or_unspecified',0))}** 个；各有 JUMP_SLOT 的分别为 {fmt(d['BIND_NOW_mapped_ELF_with_JUMP_SLOT'].get('NOW',0))}/{fmt(d['BIND_NOW_mapped_ELF_with_JUMP_SLOT'].get('lazy_or_unspecified',0))}。这里“未设全绑定”只表示允许延迟绑定，不证明实际何时解析。加载器相关节驻留前 50 见 [`loader_residency_top50.tsv`](../data/llvm_memory_budget/loader_residency_top50.tsv)。",
 '', f"LLVM 本身已定义 WEAK 导出共 {fmt(sym['defined_WEAK_export_count'])}：按互斥名称类分，模板名候选 {fmt(sym['category_counts']['template_instance_candidate'])}、其他类成员函数 {fmt(sym['category_counts']['class_member_inline_unverified'])}、vtable/typeinfo {fmt(sym['category_counts']['vtable_typeinfo'])}、其他 {fmt(sym['category_counts']['other'])}。用于可见性估算的‘类成员函数候选’跨上述模板类与其他类成员类，只按反解名含 `::` 和 `(` 取数。这是对 LLVM 全部符号的独立分类，不依赖 GCC。逐符号见 [`weak_symbols_classified.tsv.gz`](../data/llvm_memory_budget/weak_symbols_classified.tsv.gz) 和 [`weak_category_by_file.tsv`](../data/llvm_memory_budget/weak_category_by_file.tsv)。`c++filt` 名字不能证明函数真的 inline。",
 '', f"三项静态估算：① `-fvisibility-inlines-hidden` 仅取 {fmt(sym['class_member_inline_candidates'])} 个未核实类成员候选，按每个 16 B dynsym + 2 B version + 4 B hash + 名字长度加 NUL，直接表项结构字节合计上限 **{fmt(sym['structural_bytes_ceiling_kB'])} KiB**，不是可收回 Pss；② `-Bsymbolic-functions` 的“本库 `.dynsym` 已定义 FUNC 且目标为 JUMP_SLOT/GLOB_DAT”候选 **{fmt(sym['Bsymbolic_function_candidate_total'])} 条**（JUMP_SLOT {fmt(sym['Bsymbolic_function_candidate_relocations']['JUMP_SLOT'])}，GLOB_DAT {fmt(sym['Bsymbolic_function_candidate_relocations']['GLOB_DAT'])}），转成本地绑定不自动让页变干净；③ `--as-needed` 能移除的映射数 **未确定**，当前被映射 ELF 有 {fmt(sym['all_NEEDED_edges_for_mapped_ELF'])} 条 NEEDED 边，但静态符号匹配不能确认构造函数、`dlopen`、弱引用和实际提供者，需链接 map/重链实验与运行时加载清单。来源：[`symbol_estimates.json`](../data/llvm_memory_budget/symbol_estimates.json)、`relocation_targets.tsv.gz`。",
 '', '## 四、代码页热度参考','',
 '唯一 r-x 驻留前 50 文件的 `.text` 大小、驻留页数、连续段数、最长连续段及平均页间隔见 [`code_top50_pages.tsv`](../data/llvm_memory_budget/code_top50_pages.tsv)。驻留比例为驻留 `.text` 页数×4 KiB / `.text` 静态大小；跨节页计入该节的重叠页，故这是页级比例。',
 '这 50 个文件共 15,305 个 `.text` 驻留页。若**假设**每页只有 25% 热字节且能完全重排，按逐文件向上取整最少 3,844 页；若假设 50%，最少 7,665 页。对应的 45,844/30,560 KiB 只是热字节比例假设下的紧凑排布数学差额，未测量指令热度、函数边界或实际可得收益。',
 '', '## 五、优化手段与作用上限（不排序）','',
 '下表“当前 KiB”是可作用的预算池，不是该手段的收益；“未确定”表示现有单镜像静态数据无法给可得收益。所有上限都须经过同镜像只改一项的构建与运行验证。',
 '', '| 手段 | 预算类别与当前 KiB | 本次可算上限或估计 | 前提 | 主要风险 |','|---|---:|---|---|---|'])
 dirty=b['file_r--_private_dirty']+b['file_rw-_private_dirty']
 filepool=total-sum(b[k] for k in ('anon_heap','anon_unlabelled','anon_stack','anon_other_named'))
 rows_opt=[
 ('LTO',f".text {fmt(b['code_text'])}",'可得 Pss 未确定；理论上不超过整类 .text Pss','GNU ld/工程与构建链验证','构建时间、代码布局及性能变化'),
 ('-fvisibility-inlines-hidden',f"加载器节 {fmt(b['code_loader_related'])}",f"{fmt(sym['class_member_inline_candidates'])} 个候选；直接符号表结构 ≤{fmt(sym['structural_bytes_ceiling_kB'])} KiB，Pss 未确定",'GNU ld + C++ 工程','ABI / dlsym 依赖、inline 判定不充分'),
 ('按包改 -fvisibility=hidden',f"加载器节 {fmt(b['code_loader_related'])}",'可隐藏符号与 Pss 未确定','改工程导出列表','ABI、插件与符号可见性'),
 ('--exclude-libs',f"加载器节 {fmt(b['code_loader_related'])}",'可隐藏静态库导出与 Pss 未确定','GNU ld；识别归档包','ABI、动态查找'),
 ('-Bsymbolic-functions',f"文件私有脏 {fmt(dirty)}",f"本库函数目标候选 {fmt(sym['Bsymbolic_function_candidate_total'])} 条；脏页收益未确定",'GNU ld','符号插桩/覆盖语义'),
 ('延迟绑定',f"文件私有脏 {fmt(dirty)}",f"NOW 库仅 JUMP_SLOT 的页 ≤{fmt(p['now_jump_only_page_kB'])} KiB；运行后收益未确定",'GNU ld 与安全策略允许','首次调用延迟、RELRO/安全要求'),
 ('--as-needed',f"文件映射 Pss {fmt(filepool)}",f"可删除映射数未确定；当前 NEEDED 边 {fmt(sym['all_NEEDED_edges_for_mapped_ELF'])}",'GNU ld / 重链','构造函数副作用、隐式依赖'),
 ('RELR（仅 lld）',f"r-x .rel.dyn {fmt(c['.rel.dyn'])}",f"该类 Pss 理论上限 {fmt(c['.rel.dyn'])}；可得未确定",'lld 与加载器支持 RELR','兼容性、加载器升级'),
 ('合并小库',f"文件私有脏 {fmt(dirty)}",f"静态 1–2 页小库模型 {fmt(p['small_library_1to2_page_kB'])} KiB，但模型误差 >20%，可得未确定",'改工程/库边界','ABI、装载及升级粒度'),
 ('C++ 相对虚表',f"文件私有脏 {fmt(dirty)}",f"含 _ZTV 页 {fmt(p['vtable_upper_kB'])} KiB，上界与 typeinfo/未知目标重叠；可得未确定",'改 C++ ABI/工具链','ABI 与虚派发兼容性'),
 ('按热度排布函数',f".text {fmt(b['code_text'])}",'前 50 的 25%/50% 热字节假设为 45,844/30,560 KiB；非实测收益','需要剖析与链接排序','工作负载偏差、I-cache 性能'),
 ('ICF（仅 lld）',f".text {fmt(b['code_text'])}",'相同函数可折叠量未确定','lld / 工程','地址身份语义、调试'),
 ('Machine Outliner',f".text {fmt(b['code_text'])}",'可提取代码量未确定','LLVM 编译选项/工程','性能、调试及代码布局'),
 ('减少 LOAD 段','PageTables 同次值未找到；VMA 中位数 460','页表/VMA 收益未确定','链接脚本或工程','内存保护边界、兼容性')]
 for r in rows_opt:lines.append('| '+' | '.join(r)+' |')
 lines.extend(['', '### 证据边界','',
 '单次采集内的动态符号页模型高估实测 43.96%；各方法的“页上界”不能相加，也不能与 Pss 池直接相减。PageTables 同次数据、`.symtab` 已去除对象的本地表类型、真实热字节、未引用 NEEDED 的可安全删除性均未找到或未确定。需要按包重编与同镜像复测才能得到可得收益；本任务没有修改构建配置，也没有在板上执行。',
 '', '脚本执行顺序：`compute.py`（完整 ELF 和 smaps）、`weak_symbols.py`、`classify_relro.py`、`derive.py`、`build_report.py`。日志中保留首次校验失败和修正后的成功运行；最终数据以各脚本最后一次 `状态=成功` 为准。'])
 R.write_text('\n'.join(lines)+'\n')
 print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态=成功',flush=True)
if __name__=='__main__':main()
