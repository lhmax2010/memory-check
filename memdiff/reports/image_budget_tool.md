# 镜像内存预算工具：离线固化与验证

日期：2026-11-12。工具入口及用法见 [`memdiff/tools/image_budget/README.md`](../tools/image_budget/README.md)。本轮没有连接开发板；采集入口只用假数据和已保存的原始数据做测试。开发机执行采用 CPU 0、nice 19、ionice idle、Python 虚拟内存上限 2,500,000 KiB，进度和结束状态保存于离线日志。

## 实现口径

采集入口 `collect.py`：四项身份门禁；记录 clang 内核和 tvs-daemon 的 PIE/预链接标记；按 memcheck 的 10 次、30 秒、MemTotal 1%、CPU ≤21%、最长 30 分钟窗口等待；每 PID 一次 SDB shell 保存 maps/smaps/status/cmdline/exe 和每个 r-x 文件 VMA 的完整 pagemap；保存 meminfo、vmstat、zoneinfo 摘要、memory PSI；拉回文件映射的 ELF 并记录两侧 SHA256。远端返回码有独立标记；PID 退出和 ELF 拉取失败进入状态清单。采集结束要求 `sdb root off`、UID 与 boot ID 核对。

预算入口 `budget.py`：`engine/` 收录上一轮已经核验的 smaps、ELF、重定位、符号分类计算；本轮增加新采集目录的页去重与跨节分摊准备、逐进程和逐文件 Pss 明细、同次 PageTables、质量清单及通用 `budget.md`。r-x Pss 依该文件唯一驻留页的节占比折算；`file_budget.tsv` 的 r--/rw- `Private_Dirty` 是原始脏页指标，不与 Pss 相加。同路径多个 inode、脏 r-x、删除映射等不能可靠去重的页在新采集准备阶段排除，r-x Pss 归入 `code_other`；标记见 `residency_exclusions.tsv`。

对比入口 `compare.py`：按进程名和主程序路径严格配对，所有输入开机都出现才进入“配对进程”口径；全部进程另列。单侧进程、只在部分开机出现的进程分别列清单。类别、逐文件加载器节/.text/私有脏页及 ELF 指标均输出均值与差值。两边各有两次开机时，以两侧较大开机极差为噪声门槛；任一侧只有一次时标“无波动数据，差值仅供参考”。

## 离线验证

用 2026-11-11 LLVM `system_code_page_sections/` 原始采集重跑完整预算，复核脚本对已发布的 `llvm_memory_budget/` 核心 JSON 和 `derived_summary.json` 数值逐项对比：**20/20 组一致，0 不一致**，PageTables 因历史同次 `/proc/meminfo` 缺失而排除。原始 Pss=563,596 KiB、SwapPss=96,976 KiB；r-x Pss=212,919 KiB，加载器相关节=63,790.883 KiB，`.text`=112,626.217 KiB；动态重定位=1,755,115 条，readelf 错误=0。逐进程 Pss 回加为 563,596 KiB，逐文件 r-x 节 Pss 回加与 212,919 KiB 相差 0.00013 KiB（逐行六位小数舍入）。证据：`memdiff/tools/image_budget/tests/llvm11_regression.json`、`/tmp/image_budget_llvm11_validation/{derived_summary.json,process_budget.tsv,file_budget.tsv,progress.log}`；发布基准在 `memdiff/data/llvm_memory_budget/`。临时重算目录不提交。

用历史 GCC boot1 `02_steady/smaps_raw.txt.gz` 经 `tests/import_memcheck_fixture.py` 只作对比解析演练，再与 11-11 LLVM 单次预算运行 `compare.py`：严格配对键 62，GCC 单侧 41，LLVM 单侧 41；共同文件 1,595，单侧文件 207。结果全部标为单次、无波动数据；历史 memcheck 没有 pagemap，GCC 代码细分只能归 `code_other`，因此**不把这次差值写成镜像结论**。证据：`memdiff/tools/image_budget/tests/offline_compare/result/`。

单元测试 **8/8 通过**，覆盖采集中 PID 退出、ELF 拉回失败、同一路径多个 inode 的去重排除、跨节页按字节分摊、SDB 主机返回零但远端失败、CPU 边界、严格进程配对和两次开机波动判定。证据：`memdiff/tools/image_budget/tests/unit_tests.log`。

## 局限

11-11 静态重定位目标页模型预测 183,612 KiB，而同批库实测文件私脏 128,184 KiB，误差约 44%；上限不能当可得收益。历史 11-11 快照缺 `/proc/pid/exe` 和同次 PageTables，进程身份用首个 r-x 文件映射推定，PageTables 不回归。新采集脚本本轮没有上板运行，首次实际采集需检查 SDB 行为、耗时、权限与拉取缺失情况；若 ELF 拉取或 SHA 核对失败，静态细分不完整，预算质量清单会列出路径。
