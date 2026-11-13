# 镜像内存预算

BUILD_ID: `T-KSU2EJAKUC-0101-PERF-202611120549`；采集日期：2026-11-13；单次开机。单位 KiB。

用户进程 Pss 407315；SwapPss 133540；PageTables 17020。

| 互斥 Pss 类别 | KiB | 占 Pss |
|---|---:|---:|
| file_r--_private_dirty | 83720.000 | 20.55% |
| file_r--_shared_dirty_Pss | 2402.000 | 0.59% |
| file_r--_clean | 20085.000 | 4.93% |
| file_rw-_private_dirty | 21780.000 | 5.35% |
| file_rw-_shared_dirty_Pss | 955.000 | 0.23% |
| file_rw-_clean | 6581.000 | 1.62% |
| anon_heap | 37018.000 | 9.09% |
| anon_unlabelled | 39735.000 | 9.76% |
| anon_stack | 1620.000 | 0.40% |
| anon_other_named | 14078.000 | 3.46% |
| file_other | 8.000 | 0.00% |
| code_arm_unwind | 1091.637 | 0.27% |
| code_loader_related | 46427.077 | 11.40% |
| code_code_other | 6430.106 | 1.58% |
| code_plt | 3400.395 | 0.83% |
| code_rodata | 23187.098 | 5.69% |
| code_text | 98796.687 | 24.26% |

重定位、ELF 指标和驻留前 50 分别见 `relocation_summary.json`、`elf_metrics.tsv`、`code_top50_pages.tsv`。动态重定位数：1586407。逐文件 Pss 见 `file_budget.tsv`。
