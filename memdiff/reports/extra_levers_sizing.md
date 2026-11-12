# 不改业务代码的内存手段：离线条件与上限

数据：2026-11-11 LLVM 镜像，`BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611061751`；`memdiff/data/system_code_page_sections/` 的全系统文件映射、唯一 r-x 驻留页和 ELF 副本，以及 `memdiff/data/llvm_memory_budget/` 的重定位目标、ELF 节和 Pss。分析脚本与逐项表在 `memdiff/data/extra_levers_sizing/`，`progress.log` / `console.log` 记录进度与结束状态。全程离线、未连接板子；主机 CPU0、nice19、ionice idle 串行运行，Python 虚拟内存上限 2,500,000 KiB。

## 一、相对查找表

### LLVM 22.x 源码事实

本机现有 LLVM 22.1.8 发布源码快照（属于 22.x 发布系列；不是 `release/22.x` Git 分支工作树，分支最新状态未核实），文件 SHA256 和带行号摘录见 `data/extra_levers_sizing/source_files.tsv`、`llvm22_source_excerpt.txt`。`llvm/include/llvm/CodeGen/BasicTTIImpl.h:636–658` 中 `shouldBuildRelLookupTables()` 先要求位置无关、非 Medium/Large code model，然后 **649–651 行**执行 `if (!TargetTriple.isArch64Bit()) return false;`。因此 ARMv7 PIC/PIE 不运行此转换。`llvm/lib/Transforms/Utils/RelLookupTableConverter.cpp:213–215` 由 pass 调用该门禁；同文件 **57–61 行**又要求被加载的元素是 **64 位指针**。现有 32 位 ARM 镜像不符合。`BasicTTIImpl.h:642–647` 说明输出是 32 位偏移且大代码模型的 64 位架构可能超出偏移范围；从“64 位指针改为 32 位偏移”可推断大小优化对 32 位指针没有相同收益，**这是基于代码的推断，不是当时评审给出的理由**。

本机另有 LLVM 21.1.1 源码快照，其 `BasicTTIImpl.h:625–627` 已有相同的非 64 位门禁（摘录见 `llvm21_source_excerpt.txt`）。这两份发布源码包没有 Git 提交历史或评审元数据。**引入 pass 的上游提交、引入此条件的上游提交、对应评审链接与历史决策理由：未找到。**按本轮“完全离线”限制，没有访问上游站点；这项需有 llvm-project Git 历史或评审归档才能闭合。

LLVM 22.1.8 的转换对象判定见 `RelLookupTableConverter.cpp:29–129`：全局变量必须有初始化、常量、仅一次使用、local linkage、DSO local 与 implicit DSO local；唯一使用者是仅一次使用的 GEP，GEP 的唯一使用者是仅一次使用的 Load；Load 的元素必须是 64 位指针；GEP 必须可拆成零常量偏移和唯一变量偏移，步长至少为指针存储大小；每项需可常量折叠成某个全局值的固定偏移，所指对象必须是常量全局变量且具有 local linkage、DSO local 与 implicit DSO local。`206–236` 行遍历模块全局变量并转换符合者。数组是否被取地址或按下标以外方式使用，不能仅从 ELF 判定。

### ELF 候选范围

只取 `relro_target_classification.tsv.gz` 中 `.data.rel.ro` 的“字符串指针候选”和“其他函数指针候选”；同一 ELF 中以连续 4 字节重定位槽聚成区间，至少 4 项且候选占比 ≥75%。用交叉 readelf 的 `.dynsym` 排除被已定义 GLOBAL/WEAK、DEFAULT/PROTECTED 导出符号覆盖的区间；零大小导出符号起点落在区间内也排除。区间、条目数、进程数和页数见 `candidate_arrays.tsv`；去重后的逐库加权页数见 `candidate_pages_by_file.tsv`；判定脚本见 `analyze.py`。**这只确认没有可见动态导出覆盖，不证明数组在源码中是 static，也不证明满足上述 IR 的一次使用与 64 位指针条件。**

保留下来 **32,727 个候选连续区间**。按每库被映射的进程数加权，候选目标出现在页内的宽口径为 **50,832 KiB**；要求整张 4 KiB 页处于完全由候选槽组成的连续区间时为 **404 KiB**。两档页集合有包含关系，不能相加；两者都是“假如重编后这些页不再因重定位写脏”的静态上限，实际收益未确定。ARMv7 上现有 RelLookupTableConverter 被关闭，且当前 pass 要求 64 位指针，不能把这两个数当成开启现有 pass 就能取得的收益。数组地址是否外泄、是否只按下标读取，还需包源码或 LLVM IR 验证。证据 `summary.json`、`candidate_arrays.tsv`、`relro_target_classification.tsv.gz`、`relocation_pages.tsv`。

字符串指针候选最多的三个库如下。范围是各库合格区间的最小起点到最大终点，**不是一整段连续数组**；完整逐区间地址在 `candidate_arrays.tsv`。字符串样例从 ELF 中的 REL addend 指向的 `.rodata` 解码，前五条在 `top3_string_arrays.json`。

| 库 | 候选字符串指针槽 | 区间数 | 地址包络 `[起,止)` | 前五个字符串样例 |
|---|---:|---:|---|---|
| `libchromium-impl.so` | 18,112 | 3,413 | `0x41e8828–0x42c2ab0` | `not an error`; `SQL logic error or missing database`; `access permission denied`; `callback requested query abort`; `database is locked` |
| `libmali.so` | 12,957 | 208 | `0x100c304–0x104c258` | `glActiveShaderProgram`; `glActiveTexture`; `glAlphaFunc`; `glAlphaFuncx`; `glAlphaFuncxOES` |
| `libnode.so` | 3,410 | 20 | `0x931c44–0x94adf0` | `../third_party/electron_node/src/connection_wrap.cc:36`; `(wrap_data) != nullptr`; `../third_party/electron_node/src/connection_wrap.cc:37`; `(&wrap_data->handle_) == (reinterpret_cast<UVType*>(handle))`; `../third_party/electron_node/src/connection_wrap.cc:45` |

## 二、代码页预读

按 `files_from_pages.tsv` 选唯一 r-x 驻留最多的 50 个文件，从 `unique_pages.tsv.gz` 的文件偏移连续页聚段：共 **23,040 页、3,770 段**。段长度为 1 页 1,414 段、2–3 页 1,048 段、4–7 页 667 段、8–15 页 362 段、16–31 页 169 段、32–63 页 69 段、≥64 页 41 段。段起点按 4/8/16/32 页对齐的比例依次为 **25.49% / 13.45% / 7.11% / 3.93%**；恰好 16/32 页的段只有 **20/6**。对照均匀起点的 16/32 页对齐概率 6.25%/3.125%，未见 **16 页 fault-around 或 32 页块设备预读主导的统一成块特征**。这不排除局部预读：位于“16 页对齐且长度≥16”的段内的页仍占 19.87%，32 页对应 17.95%；驻留页只能显示最终状态，不能识别缺页因果。逐文件和汇总见 `top50_read_ahead.tsv`、`read_ahead_summary.json`。

这 50 个文件的 `.text` Pss 为 **60,718.55 KiB**。用每文件已驻留 `.text` 页中的**最短连续段**充当“至少真正执行了这么多页”的极端代理，按本文件 `.text` Pss/已驻留页数比例折算，保留量仅 **208.74 KiB**，得到假设可减少范围 **0–60,509.81 KiB**。上界几乎等于现有 `.text` Pss，说明该代理极弱；pagemap 无法识别执行过的指令，不能把它当成可得收益或启动时预读开销。依据 `code_file_pss.tsv`、`elf_sections_vaddr.tsv`、`unique_pages.tsv.gz`、`read_ahead_summary.json`。

后续上板只读参数清单（**本轮不执行**）：

1. `/sys/block/*/queue/read_ahead_kb`，逐设备记录；
2. debugfs 的 `fault_around_bytes`（先确认 debugfs 已挂载及路径是否存在）；
3. `/proc/mounts` 中 EROFS 挂载参数、压缩状态；若有原始镜像，离线用 EROFS 工具读压缩簇大小和 mkfs 参数。现有数据不含镜像元数据，簇大小未找到；
4. `/proc/sys/vm/` 下 `swappiness`、`page-cluster`、`vfs_cache_pressure`、`watermark_scale_factor`、`min_free_kbytes`、`compaction_proactiveness` 等实际存在项。

## 三、重复文件

`collection.json` 中 SHA256 已核对的被映射 ELF 共 1,452 个，先按哈希找不同路径，再用 `vmas.tsv` 的设备号与 inode 排除同 inode 别名。**不同 inode、内容相同且同时映射的 ELF 文件组为 0；“只保留一份驻留”的上限为 0 KiB。**逐组及逐路径表（本次只有表头）为 `duplicate_elf_groups.tsv`、`duplicate_elf_paths.tsv`。非 ELF 文件未纳入此次拉回 ELF 的去重结论。

## 四、Thumb-2 覆盖率

对 1,452 个已映射 ARM ELF，用同一交叉 readelf 读取 `.ARM.attributes` 与 `.dynsym`。仅对已定义 FUNC 的符号地址最低位计数：1 为 Thumb，0 为 ARM；不把未定义导入符号当 ARM。**31 个文件**的 `.dynsym` 已定义 FUNC 中 ARM 占比 >20%，且 `.text` >256 KiB。前 10 个按 `.text` 大小排序如下，完整表见 `arm_mode_large_text.tsv`、`thumb_coverage.tsv`；readelf 错误 0，见 `readelf_errors.tsv`。

| 文件 | ARM FUNC 占比 | `.text` KiB | 唯一 r-x 驻留 KiB |
|---|---:|---:|---:|
| `/prd/usr/lib/libbluetooth.so` | 100.0% | 9,938.6 | 4,568 |
| `/usr/apps/com.samsung.tizen.argot/bin/argot` | 100.0% | 9,823.3 | 5,536 |
| `/usr/local/lib/libavcodec.so` | 100.0% | 8,148.6 | 1,456 |
| `/usr/apps/org.tizen.tv-viewer/bin/tv-viewer` | 100.0% | 4,691.7 | 2,436 |
| `/usr/bin/issue_report_agent` | 25.4% | 3,853.6 | 2,232 |
| `/opt/usr/apps/com.samsung.tv.pisa-service/bin/adagent-service` | 100.0% | 1,484.4 | 936 |
| `/usr/apps/org.tizen.webserver/bin/liblighttpd.so` | 100.0% | 1,469.6 | 404 |
| `/opt/usr/apps/com.samsung.tv.ghservice/shared/res/libcompgamehome.so` | 100.0% | 1,171.5 | 508 |
| `/usr/lib/libc-2.40.so` | 99.9% | 1,107.3 | 1,056 |
| `/opt/usr/apps/com.samsung.tv.slive-daemon/lib/libtvs-api.so` | 100.0% | 912.8 | 916 |

`.ARM.attributes` 中声明 Thumb-2 可用不等于所有函数实际以 Thumb 编码；上表仅代表 `.dynsym` 覆盖的已定义函数，非导出的内部函数模式和整段 `.text` 的 Thumb/ARM 字节占比均**未确定**。不能据此直接估算 Thumb 化收益。

## 未闭合事项

上游引入 RelLookupTableConverter 与 32 位门禁的提交号/评审链接及历史理由：离线发布源码包不含 Git 历史，未找到。候选数组的 IR 使用方式、预读参数、实际执行热点、非 ELF 重复文件、非导出函数模式均需其他证据；本报告没有把静态上限写成可得收益。
