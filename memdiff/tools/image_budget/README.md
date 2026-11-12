# 镜像内存预算工具

同一镜像上板采集一次，离线生成预算；两份预算可逐类比较。`collect.py` 本轮只用假数据做了单元测试，**没有连接开发板**。离线计算沿用 2026-11-11 `llvm_memory_budget` 的 ELF、重定位和 Pss 分类算法；算法副本在 `engine/`，避免运行时依赖历史数据目录。

## 运行环境与命令

在 TPMS 仓库根目录运行。下面所有重负载命令固定 CPU 0、nice 19、ionice idle，Python 虚拟内存上限 2,500,000 KiB；所有输出实时写日志。`collect.py` 只使用 SDB 与板上已有的 shell、`dd`、`od`，不部署板上程序。交叉 readelf 和 c++filt 的路径见脚本顶部，来自第三轮使用的 GBS root。

```bash
mkdir -p memdiff/data/image_budget/new_image
taskset -c 0 nice -n 19 ionice -c3 bash -lc 'ulimit -v 2500000; python3 memdiff/tools/image_budget/collect.py 192.168.108.26 --out memdiff/data/image_budget/new_image/collection --expected-build-id EXPECTED_BUILD_ID 2>&1 | tee memdiff/data/image_budget/new_image/collect_console.log'
taskset -c 0 nice -n 19 ionice -c3 bash -lc 'ulimit -v 2500000; python3 memdiff/tools/image_budget/budget.py --input memdiff/data/image_budget/new_image/collection --out memdiff/data/image_budget/new_image/budget 2>&1 | tee memdiff/data/image_budget/new_image/budget_console.log'
taskset -c 0 nice -n 19 ionice -c3 bash -lc 'ulimit -v 2500000; python3 memdiff/tools/image_budget/compare.py --baseline BASELINE_BUDGET_DIR --new memdiff/data/image_budget/new_image/budget --out memdiff/data/image_budget/new_image/comparison 2>&1 | tee memdiff/data/image_budget/new_image/compare_console.log'
```

两次开机时，`--baseline` 和 `--new` 各可接两个预算目录。例如 `--baseline base_boot1 base_boot2 --new llvm_boot1 llvm_boot2 --out comparison`。一次开机只显示“无波动数据，差值仅供参考”。两次开机的差值绝对值不超过两侧较大开机极差时记“无显著差异”。

## 采集内容与安全条件

身份门禁为 armv7l、设备树含 NT72671D、cmdline 含 KSU2E、非空 BUILD_ID；可用 `--expected-build-id` 限定版本。内核是否 clang 编译单独记录。拉回 `/usr/bin/tvs-daemon`，用交叉 readelf 记录 EXEC/DYN、GNU_LIBLIST、GNU_PRELINKED、`.gnu.prelink_undo`。采集先等待开机 600 秒；每 30 秒采一次，最近 10 次 MemAvailable 和已用 Swap 极差均小于 MemTotal 的 1%，平均 CPU 忙碌率 ≤21%；最长等 30 分钟，超时标“按上限采集”。

root 只用于只读 `/proc` 与文件拉取。每个 PID 一个 SDB shell 会话，保存 maps、smaps、status、cmdline、exe，对每个 r-x 文件 VMA 一次 `dd` 整段读取 pagemap 并由 `od` 输出。保存同次 meminfo、vmstat、zoneinfo 全文与摘要、memory PSI。拉回所有带文件路径的映射，保留 ELF，记录板上与主机 SHA256。每个远端命令在输出尾部带显式返回码标记，采集期间退出的进程记录后跳过；最后 `sdb root off` 并核对 UID 与 boot ID。`collection.json`、`raw/`、`elf/`、`zoneinfo_summary.txt` 和 `collect.log` 是原始证据。

## 预算输出和口径

- `budget.md`、`derived_summary.json`：互斥类别 Pss、SwapPss、同次 PageTables、分布与主要静态上界。所有内存量单位为 KiB。
- `smaps_budget.json`、`code_budget.json`、`process_budget.tsv`、`file_budget.tsv`：逐映射 Pss；r-x Pss 按该文件唯一驻留页的 ELF 节字节比例折算。文件 r--/rw- 私有脏页另保留原始 `Private_Dirty`，不与 Pss 混加。
- `relocation_targets.tsv.gz`、`relocation_pages.tsv`、`relro_target_classification.tsv.gz`、`relocation_summary.json`：动态重定位类型、目标页和可辨认的 vtable/typeinfo 标签。
- `elf_metrics.tsv`、`symbol_estimates.json`：动态符号、各表大小、DT_NEEDED、PIE、BIND_NOW 与静态候选估计。
- `code_top50_pages.tsv`：唯一 r-x 驻留前 50 文件的 `.text` 页连续段和假设紧凑下界。
- `progress.log`：离线分析进度和结束状态。输入采集目录里的 `section_residency.tsv`、`unique_pages.tsv.gz` 是可复核的中间表。

对比输出包括 `category_comparison.tsv`（全部进程与严格配对进程）、`one_sided_processes.tsv`、`intermittent_processes.tsv`、四个逐文件差值前 50 表、`elf_comparison.tsv`、`comparison.md` 和 `comparison.json`。严格配对按进程名与主程序路径，要求所有输入开机都存在；同名多个实例先按该键合并。历史 11-11 数据缺 `/proc/<pid>/exe`，用首个 r-x 文件映射推定主程序，在元数据中标明。

## 已知局限

重定位目标页×映射进程数是静态模型：在 11-11 数据上预测 183,612 KiB，同批库实际文件私有脏页 128,184 KiB，按实测作分母的误差约 44%；这些页数不能直接当收益。vtable、typeinfo 和 `<256 B` 页标签可重叠；无 `.symtab` 时大部分指针容器不可确定。r-x Pss 逐映射取整；同路径多个 inode、脏 r-x、已删除映射的唯一页归属被排除，回退为 `code_other`。ELF 拉取失败会在 `collection.json` 留状态，相关静态细分不完整。PageTables 只有本次采到 meminfo 才填写；历史 11-11 没有同次值。不同镜像的服务、采集时刻与工作负载差异不能归因于编译器。

## 离线验证

`tests/llvm11_regression.json` 比较已发布 11-11 预算的 20 组核心结果，PageTables 除外；`tests/offline_compare/` 用历史 GCC boot1 `02_steady/smaps_raw.txt.gz` 和 11-11 LLVM 单次预算验证单侧进程及文件的处理。历史 memcheck 没有 pagemap，测试适配器把 GCC r-x 归为 `code_other`，输出只验证解析/对比，不作为跨镜像结论。运行单元测试：

```bash
taskset -c 0 nice -n 19 ionice -c3 bash -lc 'ulimit -v 2500000; python3 -m unittest discover -s memdiff/tools/image_budget/tests -p "test_*.py" -v'
```
