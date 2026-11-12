#!/usr/bin/env python3
"""Render the prelink tool validation report from saved evidence."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
MEMDIFF=HERE.parents[1]
OUT=MEMDIFF/'reports/prelink_tool_validation.md'
def rows(name):
 with (HERE/name).open() as f:return list(csv.DictReader(f,delimiter='\t'))
def link(name):return f'[{name}](../data/prelink_tool_validation/{name})'

def main():
 manifest=json.loads((HERE/'build_manifest.json').read_text())
 dep=json.loads((HERE/'dependency_summary.json').read_text())
 integrity=json.loads((HERE/'root_integrity_summary.json').read_text())
 faithful=rows('verify_summary.tsv'); alias=rows('alias_verify_summary.tsv')
 top=rows('mismatch_sections_top20.tsv'); undo=rows('undo_results.tsv')
 tifs=rows('tifs_interp_trials.tsv')
 lines=[
  '# GCC 已预链接 ELF 与上游 prelink-cross 逐字节核对',
  '',
  '## 范围与根目录完整性',
  '',
  '本次未上板、未连接 VD 网络；只从公开 `https://git.yoctoproject.org/prelink-cross.git` 取源码，'
  '构建依赖从公开 Ubuntu 包下载并**仅解包到仓库外**。使用 GCC 板上拉回的 '
  '[1463 个 ELF 副本](../data/gcc_baseline/elf/files) 原路径组装 `/tmp/prelink-tool-validation-20261112/gcc-root`，'
  '照用户提供的 8 行写入 `etc/prelink.conf`。原始复制过程见 '+link('root_assembly.log')+'；'
  '根目录中 1463/1463 个 ELF 与仓库副本 SHA256 相同，见 '+link('root_integrity_summary.json')+'、'+link('root_integrity.tsv')+'。'
  'GCC 的 [ELF 标记表](../data/system_code_page_sections/elf_summary.tsv) 有 **425 个**带预链接标记（含 10 个 GNU_LIBLIST 主程序），均进入验证和撤销清单。',
  '',
  '保存的 ELF 不是完整镜像根：缺少 SONAME 文件名链接和若干实际依赖文件。'
  '原样根保留这一缺口。另建一个**仅用于诊断**的根目录，依据每个副本自身的 `DT_SONAME` 唯一对应关系'
  '添加 681 个软链接，没有合成或修改任何 ELF 字节；清单见 '+link('inferred_aliases.tsv')+'。'
  '来自目标 ELF 的 NEEDED 中，315 个不同链接名在原样根缺失，引用边共 7059 条，见 '+link('missing_soname_aliases.tsv')+'。'
  '这类推定链接不能证明与 VD 完整镜像的文件名空间逐项相同。',
  '',
  '## 一、源码版本与构建',
  '',
  '| 源码线 | 提交 | 日期 | 用途 |',
  '| --- | --- | --- | --- |',
  f"| master 中最接近 2013-05-03 | `{manifest['nearest_2013_overall_master']['commit']}` | {manifest['nearest_2013_overall_master']['date']} | 无交叉 `--root/--rtld`，只记录 |",
 ]
 for r in manifest['builds']:
  purpose={'cross_2013':'最接近 2013-05-03 的可用 cross 分支版本',
           'cross_latest':'cross 分支最新版本（诊断对照）',
           'master_2024':'仓库当前 master；不支持交叉根/rtld'}[r['version']]
  lines.append(f"| {r['version']} | `{r['commit']}` | {r['commit_date']} | {purpose} |")
 lines += [
  '',
  '`master` 与 `cross_prelink` 是不同源码线。为满足“可用交叉工具”和“当前主线”两个要求，'
  '实际编译了 2013 cross、最新 cross 和当前 master 三版；当前 master 没有 `prelink-rtld`，'
  '也拒绝 `--root`。2013/2019 cross 版都能处理 ARM ELF、支持 `--root/--rtld`，'
  '但都**不支持** VD 包里的 `--ignore-soname`，故验证命令只能省略这一 VD 私有选项。'
  '源码 `src/main.c` 的选项表以及 '+link('help_cross_2013.txt')+'、'+link('help_cross_latest.txt')+'、'+link('help_master_2024.txt')+' 可复核。',
  '',
  '全部工具为 x86_64 主机程序，留在 `/tmp/prelink-tool-validation-20261112/build-*/src/`，不入库、不安装系统目录。'
  '构建参数为 `--disable-selinux --disable-dependency-tracking --prefix=/tmp/.../install-<版本>`，'
  '`CPPFLAGS=-I/tmp/.../deps/usr/include`、`LDFLAGS=-L/tmp/.../deps/usr/lib/x86_64-linux-gnu`；'
  '执行 `make -C src -j1`，CPU0/nice19，虚拟内存上限 2,500,000 KiB。'
  '源码提交、二进制 SHA256 和依赖包版本/SHA256 在 '+link('build_manifest.json')+'、'+link('tool_versions.tsv')+'；'
  '配置/编译原始日志为 `autoreconf_*.log`、`configure_*.log`、`build_*.log`。'
  '2013 完整 `make -j1` 曾因文档所需 `fig2dev` 缺失退出；随后 `make -C src -j1` 成功并产出两个工具，见 '
  +link('build_2013.log')+' 与 '+link('build_2013_tools.log')+'。',
  '',
  '## 二、425 个文件的逐字节核对',
  '',
  '上游 `--verify` 的源码语义是：撤销预链接、重新预链接，把**重建的预链接文件**与输入文件按大小和字节比较；'
  '标准输出则是**撤销后的文件**，不能拿 stdout 直接和预链接输入比较。'
  '这里把内部比较返回成功记为“逐字节一致”，明确报 `prelinked file size differs` 或 `prelinked file was modified` '
  '记为“不一致”，其余记为“报错”。依据为 cross 分支 `src/verify.c` 的 `prelink_verify`，原始逐文件结果见 '
  +link('verify_results.tsv')+' 和 '+link('alias_verify_results.tsv')+'。',
  '',
  '| 根目录 / 工具 | 一致 | 不一致 | 报错 | 合计 |',
  '| --- | ---: | ---: | ---: | ---: |',
 ]
 for name,data in [('原样 GCC 副本根',faithful),('推定 SONAME 链接的诊断根',alias)]:
  for r in data:
   lines.append(f"| {name} / {r['version']} | {r['byte_identical']} | {r['byte_different']} | {r['error']} | {r['total']} |")
 lines += [
  '',
  '原样根中两版 cross 都仅 4 个一致、`libc-2.40.so` 1 个文件大小不一致、420 个报错；'
  '诊断根中大量报错转为文件大小不一致。当前 master 的 425 个报错均为不支持 `--root`，不能据此评价它的 ARM 重定位实现。'
  '前两版的逐项 stderr 原文见 '+link('verify_stderr.log')+'、'+link('alias_verify_stderr.log')+'；'
  '根目录原始 ELF 字节在验证后仍 1463/1463 相同。'
  '两种根目录的失败不能单独归因于 VD 工具实现：原样根缺依赖文件名，诊断根的软链接是推定的，'
  '且上游缺 VD 的 `--ignore-soname` 和可能存在的 VD 补丁。**尚未证明任何上游版本与 VD 出镜像工具逐字节等价。**',
  '',
  '### 诊断根前 20 个不一致文件的 ELF 节',
  '',
  '为定位差异，只在仓库外另编一个**诊断副本**，在 `--verify` 的内部比较前把重建文件另存；'
  '不用于上表计数。唯一源码改动见 '+link('verify_capture.patch')+'，工具 SHA256 见 '
  +link('diagnostic_capture_tool.sha256')+'。逐节比较基于交叉 `readelf -SW` 的节大小及节内容字节，'
  '`.gnu.libstr` 的 +9/+14 字节等是**重建副本相对 GCC 输入**的差，不推断成 VD 工具的具体补丁效果。'
  '完整节表见 '+link('mismatch_readelf_top20.txt.gz')+'、逐文件 SHA256 与头部/填充差见 '
  +link('mismatch_sections_top20.tsv')+'。',
  '',
  '| 文件 | 文件大小差 B | 内容不同的节 | 节大小差 B |',
  '| --- | ---: | --- | --- |',
 ]
 for r in top:
  delta=int(r['recreated_bytes'])-int(r['original_bytes'])
  lines.append(f"| `{r['path']}` | {delta:+d} | `{r['changed_sections']}` | `{r['section_size_deltas'] or '无'}` |")
 lines += [
  '',
  '### 撤销预链接',
  '',
  f"在独立根副本逐文件执行 2013 cross `prelink --root=<副本> -u`：**{sum(r['status']=='success' for r in undo)}/{len(undo)}** 个返回成功，"
  '撤销后均无 `.gnu.prelink_undo/.gnu.liblist/.gnu.conflict` 或 `GNU_PRELINKED/GNU_LIBLIST/CHECKSUM` 标记，'
  '交叉 readelf 均可解析。撤销前后每文件大小与返回码见 '+link('undo_results.tsv')+'，日志见 '
  +link('undo_progress.log')+'、'+link('undo_stderr.log')+'。只改仓库外的撤销副本。',
  '',
  '## 三、TIFSDaemon 的 NEEDED 闭包与补目录试验',
  '',
  f"在已保存的 1463 个 ELF 中，19 个目标有 **{19-dep['missing_target_copies']}** 个可执行文件副本，另 8 个缺失；"
  '因此不能宣称查清全部 19 个目标的依赖。缺失的 8 个目标在 '+link('missing_copies.tsv')+' 单列。'
  '`TIFSDaemon` 可静态追到 **284** 个保存的 ELF 路径。它直接 NEEDED `libfkp.so.0`，'
  '后者的保存副本 `/usr/lib/libfkp.so.0.1.0` NEEDED `libfkpInternal.so`；'
  '唯一保存文件是 **`/opt/usr/apps/Ddrm/fkp/lib/libfkpInternal.so`**，'
  '这个目录既不在原 `--ld-library-path`，也不在 8 行 `prelink.conf`。'
  '此外 `TIFSDaemon` 直接 NEEDED 的 `libcamera-control.so` 位于 `/hal/lib/`，也在两份目录之外。'
  '证据 '+link('elf_dynamic.tsv')+'、'+link('dependency_edges.tsv')+'、'+link('outside_ld_path.tsv')+'；'
  '按保存副本能确认有目录外库的目标**只有 TIFSDaemon**，其余 8 个缺副本目标仍未确定。',
  '',
  '`libfactory-interface.so` 是 TIFSDaemon 的直接 NEEDED，保存的 GCC ELF 副本里**没有**同名文件或 SONAME 匹配文件；'
  '已存在的 `libfactory-interface-ATSC.so` 无此 SONAME，不能冒充。'
  '缺失文件和 SONAME 别名见 '+link('missing_copies.tsv')+'、'+link('missing_soname_aliases.tsv')+'。'
  '用户给出的 VD 出镜像日志已证实当时的首个报错为 `libfkpInternal.so`；本轮不以不完整副本替代该实际日志。',
  '',
  '在独立根副本分别试了原目录、仅加 FKP 到 `--ld-library-path`、同时加到 `prelink.conf`、'
  '再加 `/hal/lib` 的组合。为了区分解释器路径缺口，诊断试验另根据 TIFSDaemon 的 `PT_INTERP=/lib/ld-linux.so.3` '
  '及保存的 `/usr/lib/ld-linux.so.3` 建了一个**推定解释器软链接**，记录在 '+link('interpreter_alias.txt')+'。'
  '即便如此，五种组合都先报保存根缺 `libfactory-interface.so`；目标 SHA256 未变、无预链接标记。'
  '`prelink -fm` 在这种失败下仍返回 **0**，所以退出码不能单独作为成功判据。逐次命令、输出、SHA256 和标记见 '
  +link('tifs_interp_trials.tsv')+'、`tifs_interp_*.log`；原样根对照见 '+link('tifs_trials.tsv')+'。'
  '**补入 FKP 目录后 TIFSDaemon 仍未预链接；是否还需把目录加到 `prelink.conf` 为未确定。**'
  '需要保存完整 GCC 根（至少补齐 `libfactory-interface.so` 及真实软链接）和 VD 包自身的 prelink/rtld 才能区分。',
  '',
  '## 已闭合与挂账',
  '',
  '- 已闭合：三条源码线与两版可用 cross 工具、425 文件逐字节内部核对、425 文件撤销验证、TIFSDaemon 的 FKP 路径及目录缺口；证据分别见本报告上述表格和数据文件。',
  '- 未确定：上游与 VD 私有 prelink/rtld 的逐字节等价；TIFSDaemon 补目录后能否成功，以及是否必须同时改 prelink.conf；8 个缺副本目标的目录外依赖。没有开发板或 VD 网络检查。',
  '',
 ]
 OUT.write_text('\n'.join(lines))
 print(f'wrote {OUT} {OUT.stat().st_size} bytes',flush=True)

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException:
  status='失败';raise
 finally:print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+status,flush=True)
