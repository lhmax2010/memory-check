# 镜像内存预算

BUILD_ID: `T-KSU2EJAKUC-0101-PERF-202611120549`；采集日期：2026-11-13；单次开机。单位 KiB。

用户进程 Pss 407723；SwapPss 132152；PageTables 16940。

| 互斥 Pss 类别 | KiB | 占 Pss |
|---|---:|---:|
| file_r--_private_dirty | 82928.000 | 20.34% |
| file_r--_shared_dirty_Pss | 2404.000 | 0.59% |
| file_r--_clean | 20423.000 | 5.01% |
| file_rw-_private_dirty | 21572.000 | 5.29% |
| file_rw-_shared_dirty_Pss | 950.000 | 0.23% |
| file_rw-_clean | 6737.000 | 1.65% |
| anon_heap | 37317.000 | 9.15% |
| anon_unlabelled | 40655.000 | 9.97% |
| anon_stack | 1736.000 | 0.43% |
| anon_other_named | 12606.000 | 3.09% |
| file_other | 8.000 | 0.00% |
| code_arm_unwind | 1138.999 | 0.28% |
| code_loader_related | 46816.238 | 11.48% |
| code_code_other | 5601.747 | 1.37% |
| code_plt | 3427.186 | 0.84% |
| code_rodata | 23441.140 | 5.75% |
| code_text | 99961.691 | 24.52% |

重定位、ELF 指标和驻留前 50 分别见 `relocation_summary.json`、`elf_metrics.tsv`、`code_top50_pages.tsv`。动态重定位数：1597108。逐文件 Pss 见 `file_budget.tsv`。
