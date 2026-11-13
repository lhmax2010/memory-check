# noPIE 新镜像后续验证（2026-11-13）

本轮镜像 `T-KSU2EJAKUC-0101-PERF-202611120549`，板子 `192.168.108.26`，`armv7l / NT72671D / KSU2E`；内核为 clang 22.1.8 编译。T0/T1 同一 boot ID `2cf21223-81d9-4623-81da-c556dcf62577`，没有重启、改写系统 ELF 或设置。板钟为 `-0800`，主机记录为 `+0800`，所以事件以 boot ID 和主机日志排序，不直接比较两台机器的墙钟。原始身份见 [T0_identity.txt](../data/noPIE_followup_validation/T-KSU2EJAKUC-0101-PERF-202611120549/20261113_followup/T0_identity.txt)，命令及返回码见同目录 `T0_commands.json`、`T1_commands.json`。主机执行脚本为 [nopie_followup_board.py](../scripts/nopie_followup_board.py)、[nopie_followup_offline.py](../scripts/nopie_followup_offline.py)。

## 一页结论与阶段 A–D checkpoint

| 项目 | 状态 | 证据及边界 |
|---|---|---|
| A 身份、19 目标静态状态 | PASS | BUILD_ID、身份、19 条 ELF/RPM 见 [identity_and_build_evidence.tsv](../data/noPIE_followup_validation/T-KSU2EJAKUC-0101-PERF-202611120549/20261113_followup/identity_and_build_evidence.tsv)；完整产品/Base 构建来源、LTO/MLGO 逐包执行证据 **BLOCKED**。 |
| B 预链接构建与 TIFSDaemon | 部分完成 | 18/19 目标的静态标记与 418 个带标记库沿用 [第一部分报告](noPIE_prelink_validation.md)；本镜像 prelink 构建日志未取得，TIFSDaemon 首个实际报错未确认。 |
| C 健康与进程可比性 | 部分完成 | T0/T1 均 6 个失败单元、未观察到新增 crash 文件或筛选信号；acm-service 仍缺席。共同进程集合重算见 [process_group_summary.tsv](../data/noPIE_followup_validation/T-KSU2EJAKUC-0101-PERF-202611120549/20261113_followup/process_group_summary.tsv)。历史同项健康基线缺失。 |
| D TEXTREL | 部分完成 | 已拉回的映射 ELF：noPIE 1/1385、GCC 1/1463、旧 LLVM 1/1403，均为 `/usr/bin/bt-service`；没有当前 BUILD_ID 全 rootfs，不能称全镜像无新增。见 [textrel_scan.tsv](../data/noPIE_followup_validation/T-KSU2EJAKUC-0101-PERF-202611120549/20261113_followup/textrel_scan.tsv)。 |
| E HEVC | BLOCKED | 板上未找到 `.h265/.hevc` 测试媒体；`ffmpeg` 不在 PATH；`gst-inspect-1.0 avdec_h265` 返回“No such element or plugin”。没有做无效试跑或编造 FPS。原始见本轮 `T0_media.txt`。 |

### A. 镜像与重编证据

`/etc/os-release` 的 BUILD_ID 是板上镜像身份，不能反推出产品和 Base 仓库快照。`rpm -qa` 可见 glibc `2.40-1.99`、tizen-release `10.0.0-1.24`；抽查的 RPM `BUILDTIME` 均为 0，不能用作构建时间。板上无 clang/llvm 编译器 RPM；内核编译器版本不能作为用户空间编译证据。19 个目标在 [targets19.tsv](../data/noPIE_prelink_validation/targets19.tsv) 全为 ET_EXEC、`.comment` 同时有 GCC 14.2.0 和 clang 22.1.8；这只证明文件含这两类注释，不证明全产品重编或实际 clang driver 关闭默认 PIE 的参数。目标所属 RPM 见本轮 `target_rpms.txt`，逐项合并见 `identity_and_build_evidence.tsv`。LTO/MLGO 的配置声明来自交付背景，13 个对象静态节确有变化（[static_13_vs_llvm1111.tsv](../data/noPIE_prelink_validation/static_13_vs_llvm1111.tsv)），但缺构建日志，逐包实际使用状态未确认。需要对应 BUILD_ID 的产品/Base snapshot manifest、build.conf、clang driver 输出和关键包 build.log；本轮未拉源码或重建。

### B. prelink 与 TIFSDaemon

新镜像静态标记为 18/19 程序、418 个库；`TIFSDaemon` 为唯一无 `GNU_LIBLIST` 与 `.gnu.prelink_undo` 的目标，见 [第一部分报告](noPIE_prelink_validation.md) 及其 `targets19.tsv`。本轮未找到对应镜像的 prelink 构建日志，**不能确认其失败发生在哪一步**。历史 GCC 出镜像日志首个报错为 `libfkpInternal.so` 不可打开；保存的 GCC 闭包显示它位于 `/opt/usr/apps/Ddrm/fkp/lib/`，不在历史 `--ld-library-path` 和 prelink.conf 八个目录，另有 `/hal/lib/libcamera-control.so` 在目录外，见 [prelink_tool_validation.md](prelink_tool_validation.md) 第三节。本轮 `T0_tifs.txt` 证实当前运行中的 TIFSDaemon 映射了这两个库，但这不证明新镜像构建时的同一原因，也不能区分随后替换 ELF。修复定位建议是核对本镜像 prelinksh 的逐目标日志和 FKP 包安装路径，再决定是否调整构建时搜索目录；本轮未改板端路径。

运行时诊断矩阵：18 个带静态标记的目标中，仅 `/usr/bin/pulseaudio --version` 在上一轮取得 `prelink checking: ok`（[原始输出](../data/noPIE_prelink_validation/probe_raw/diagnostic_pulseaudio.stdout)）；其余 17 个没有安全短命令的运行时证据。TIFSDaemon 静态未标记，运行时未尝试。该 pulseaudio 诊断只覆盖那一次短命令，不能代表常驻 daemon 实例。未为了诊断重复启动生产服务。

### C. 健康、失败单元与固定/共同集合

T0/T1 的失败单元均为 `com.samsung.tv.qse-daemon.service`、`kzram.service`、`org.tizen.mbr-daemon.service`、`security-emdaemon.service`、`ses-usb-installer@sda1.service`、`vdca-update.service`；清单无新增。`org.tizen.acm-service.service` 为 `inactive/dead`、`Result=success`、`NRestarts=0`，未手动启动。九个其余指定程序均在进程列表。三个 crash 目录在 T0/T1 均未列出文件；不能外推为从未崩溃。`journalctl` 过滤无命中且返回 1，不能当作服务无问题的证据。健康窗口的逐行比较及返回码见 `health_t0_t1_summary.json`、`T0/T1_*.txt` 和命令 JSON。11-11 没有同项健康快照，六个失败单元是否比旧镜像新增仍未确定。

按原 `classification.json` 的固定 15 路径、逐映射 smaps 的 Pss+SwapPss 复算，GCC 两次为 74,668/74,496 KiB，LLVM 第三轮 85,594/85,688 KiB，新镜像 69,422/69,358 KiB，与 [noPIE 第一部分汇总](../data/noPIE_prelink_validation/three_image_comparison.tsv) 一致。成员表 [fixed15_presence.tsv](../data/noPIE_followup_validation/T-KSU2EJAKUC-0101-PERF-202611120549/20261113_followup/fixed15_presence.tsv) 显示 `acm-service` 仅 GCC 两次存在，LLVM 第三轮和新镜像两次均缺席；因此固定组差值包含服务集合差，不能全归于编译或预链接。

严格配对定义为 `(进程名, 主程序路径)` 在上述六个快照**各恰好出现一次**，不跨启动配 PID。共同身份为 94 个；GCC 两次 Pss+SwapPss 为 **515,309/502,846 KiB**，LLVM 第三轮 **518,574/511,505 KiB**，新镜像 **489,377/488,412 KiB**。新镜像相对 GCC/LLVM3 的均值差分别为 **−20,183/−26,145 KiB**；各侧两次观察极差 GCC 12,463、LLVM3 7,069、新镜像 965 KiB。这是更严格但更窄的服务集合，仍有工作负载和 LTO/MLGO 差异。完整逐进程复算见 `process_smaps_same_source.tsv`、`strict_common_processes.tsv`；新镜像采集只保留完整进程 106/105 个，历史原始 smaps 含内核/退出附近进程，故其“全部进程数”不可直接比较。共同集合是六次都可唯一匹配的交集，不是删去异常服务后的“编译器收益”。

### D. TEXTREL 覆盖与差异

用指定 ARM 交叉 readelf 对已拉回、非软链接 ELF 查 `DT_TEXTREL` 和 `DT_FLAGS` 的 `TEXTREL`，每个文件保留规范路径和 SHA256；三个集合分别成功解析 1,385/1,463/1,403 个，解析失败 0。唯一带标记的当前文件 `/usr/bin/bt-service` 两个入口均为真；GCC 与 LLVM3 同路径也均为真，因此在这个**共同已取得路径**上新增 0、消除 0。文件哈希不同，不能据此推断二进制相同。逐文件及跨镜像分类见 `textrel_scan.tsv`、`textrel_current_diff.tsv`。这些集合来自运行时映射 ELF 的拉回副本，未取得完整 rootfs；未映射 ELF 的 TEXTREL 状态为未确定，不能给全镜像覆盖率或全镜像新增数。`bt-service` 所属包及写入代码段的实际重定位尚未核查，本轮不将其归因 PIE/LTO。

### E. HEVC 有效性和有界复测

实际 TPMS GStreamer HEVC 脚本使用 `h265parse ! avdec_h265 ! fakesink sync=false`，并用固定 1000 帧除以整秒，不检查 gst-launch 返回码或 EOS（[`test_h265.sh`](../../performance/script/gstreamer_benchmark_test/target/test_h265.sh)）；FFmpeg 脚本使用 `ffmpeg -nostdin -nostats -threads N -benchmark -c:v hevc -i INPUT -f null -` 并从 `fps=` 提取数值（[`ffbench.sh`](../../performance/script/ffmpeg_benchmark_test/target/ffbench.sh)）。当前板上 `find /opt/usr /opt/share /usr/share` 未发现目标媒体，`ffmpeg` 命令缺失，`gst-inspect-1.0 avdec_h265` 显示无插件；原始输出见本轮 `T0_media.txt`。因此两项均 **0 次有效、0 次失败尝试、均值/中位数未定义**；本轮在试跑前停下，没有设置超时预算或重复运行。旧 GCC/LLVM 的 HEVC 有 SIGABRT 和缺完整工作量证据，不能作为合格对照，见 [final_gcc_vs_llvm.md](final_gcc_vs_llvm.md) 的 HEVC 质量段。要复测需提供同一媒体的 SHA256/编码信息、可运行的 FFmpeg 和对应 gst-ffmpeg/avdec_h265 插件部署方案及其解码路径，再固定超时和最多 5 次尝试；本轮未安装依赖或变更负载。

## 上周代办与下一步

构建/prelink：静态恢复已证实，构建日志缺失。两启动专项：上一轮完成，非同镜像控制实验。正式 TPMS：本轮未执行。HEVC：链路阻塞。TEXTREL：已映射 ELF 范围扫描完成，完整镜像仍缺。若把 noPIE 镜像作为候选，需要先补齐产品/Base 构建来源、逐包 LTO/MLGO 证据、失败单元历史基线与 HEVC 可用链路，再决定正式 TPMS 的测试条件。若产品主线保留 PIE，应等待 **PIE+LTO+MLGO** 的基线做正式比较；本报告不代表关闭 PIE 已获产品批准或被否决。

板端最后 `sdb root off` 后 UID 为 **5001**，boot ID 未变；没有创建板端文件，也无临时设置需要恢复。敏感的原始进程、journal/dmesg、crash 路径输出只保存在本地 `data/noPIE_followup_validation/.../20261113_followup/T0_*.txt` 和 `T1_*.txt`，不上传系统 ELF、媒体或原始日志。主机完成时间以 `T1_progress.log`、脚本结束行为准。
