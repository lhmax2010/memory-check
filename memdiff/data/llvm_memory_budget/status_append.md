
### LLVM 保留 PIE、无预链接条件下的自身内存预算（2026-11-12）

计划与进度：完全离线复用 2026-11-11 LLVM 板 `BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751` 的 `memdiff/data/system_code_page_sections/` 全系统 maps/smaps/pagemap 与 1452 个原样拉回 ELF，第三轮 LLVM 两次开机仅作量级参照；不使用 GCC 对比、不上板、不改构建。开发机 CPU0/nice19/ionice3 串行，Python 虚拟内存上限 2.5 GB。脚本、逐 ELF/逐页/逐进程表及实时进度在 `memdiff/data/llvm_memory_budget/`，报告 `memdiff/reports/llvm_memory_budget.md`。

已闭合：322 个原始 PID 中 316 个完整，111 个有用户 VMA；同次快照 Pss=563596 KiB、SwapPss=96976 KiB。r-x Pss=212919 KiB，按唯一页节占比折算后 `.text`=112626.2、加载器相关节=63790.9 KiB；文件 r--/rw- 私有脏合计 133700 KiB。1452 个 ELF 动态重定位 1755115 条，交叉 readelf 无错误；静态可写目标页×映射进程预测 183612 KiB，同批库实测文件私脏 128184 KiB，逐库绝对误差/实测为 43.96%，故预测不作为可得收益。vtable/typeinfo 标签页 22680/23644 KiB，交集 22204 KiB；目标字节 <256 B 页 65348 KiB，均为重叠的静态上界。NOW/BIND_NOW ELF 92 个、其余 1360 个；WEAK 定义导出 198643 个，类成员函数候选 161913 个；`-Bsymbolic-functions` 本库函数目标候选 200066 条，`--as-needed` 可删映射数未确定。证据 `derived_summary.json`、`relocation_summary.json`、`relro_classification_summary.json`、`symbol_estimates.json` 与报告各表。

质量与挂账：`qa.json` 的五项检查全通过，新的 ELF 路径、GLOBAL/WEAK/未定义符号个数及主要节大小与前次独立 readelf 表逐文件一致，Pss 分类合计等于总 Pss。11-11 同次 `/proc/meminfo` 未采到，PageTables 只能列第三轮 16164/16052 KiB 作量级参照；6 个采集期间退出或不完整 PID 不在预算内。多数 `.data.rel.ro` 目标容器不能由已保存的 `.dynsym` 确定；热字节、可安全删除的 NEEDED 及各优化手段实际收益均需另行重编与同镜像实测。本次不排序、不下超出数据的收益结论。
