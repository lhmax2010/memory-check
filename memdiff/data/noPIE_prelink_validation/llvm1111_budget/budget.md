# 镜像内存预算

BUILD_ID: `T-KSU2EJAKUC-0101-PERF-202611061751`；采集日期：2026-11-11；单次开机。单位 KiB。

用户进程 Pss 563596；SwapPss 96976；PageTables 未找到。

注意：6 个映射路径拉取失败或 SHA256 未核对，静态 ELF 细分可能不完整；见 `collection_quality.json`。

| 互斥 Pss 类别 | KiB | 占 Pss |
|---|---:|---:|
| file_r--_private_dirty | 103420.000 | 18.35% |
| file_r--_shared_dirty_Pss | 1898.000 | 0.34% |
| file_r--_clean | 19679.000 | 3.49% |
| file_rw-_private_dirty | 30280.000 | 5.37% |
| file_rw-_shared_dirty_Pss | 565.000 | 0.10% |
| file_rw-_clean | 8676.000 | 1.54% |
| anon_heap | 77846.000 | 13.81% |
| anon_unlabelled | 84809.000 | 15.05% |
| anon_stack | 2516.000 | 0.45% |
| anon_other_named | 20968.000 | 3.72% |
| file_other | 20.000 | 0.00% |
| code_arm_unwind | 1232.662 | 0.22% |
| code_loader_related | 63790.883 | 11.32% |
| code_code_other | 4853.840 | 0.86% |
| code_plt | 4329.104 | 0.77% |
| code_rodata | 26086.294 | 4.63% |
| code_text | 112626.217 | 19.98% |

重定位、ELF 指标和驻留前 50 分别见 `relocation_summary.json`、`elf_metrics.tsv`、`code_top50_pages.tsv`。动态重定位数：1755115。逐文件 Pss 见 `file_budget.tsv`。
