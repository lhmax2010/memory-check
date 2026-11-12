#!/usr/bin/env python3
"""Write the A/B report from saved gates and measured TSVs, without estimates."""
import csv, json
from pathlib import Path
import preflight as p

HERE=p.HERE
M=HERE.parents[2]
REPORT=M/'reports/prelink_undo_ab.md'
STATES=('factory','programs_undone','all_undone')

def rows(name):
 with (HERE/name).open() as f:return list(csv.DictReader(f,delimiter='\t'))

def link(path,label=None):
 return f'[{label or path.name}](../data/prelink_undo_ab/attempt2/{path.relative_to(HERE).as_posix()})'

def fmt(v):return f'{float(v):,.1f}'

def main():
 old=REPORT.read_text()
 if '# GCC PERF 镜像预链接撤销对照：准备阶段停止记录' not in old:
  raise RuntimeError('prior stop record not found; refusing to overwrite it')
 boot=rows('per_boot_metrics.tsv');delta=rows('state_deltas.tsv');pages=rows('pagemap13_loader_residency.tsv')
 changes={(r['state'],r['metric']):r for r in delta}
 sel=rows('pull_classify.tsv')
 exclusions=[r for r in sel if r['category'] in ('program','library') and r['selected']!='1']
 selection=[r for r in sel if r['selected']=='1']
 health=[]
 for state in STATES:
  for i in (1,2):
   tag=f'{state}_{i}';folder=HERE/'boots'/tag
   h=json.loads((folder/'health.json').read_text())
   d=json.loads((folder/'prelink_diagnostic.json').read_text())
   health.append((tag,h,d))
 recovery=json.loads((HERE/'recovery/recovery_result.json').read_text())
 report=[]
 def add(*lines):report.extend(lines)
 add('# GCC PERF 同镜像预链接撤销对照', '',
     '采集日期：2026-11-12，KantSU2E GCC PERF，BUILD_ID `T-KSU2EJAKUC-0101-PERF-202610010416`。',
     f'板上原件与 11 月 2 日副本匹配：{sum(r["matches_old"]=="1" for r in sel)}/{sum(r["old_sha256"]!="" for r in sel)} 个已存副本；其余旧副本缺失，并非内容不符。证据：{link(HERE/"pull_classify.tsv")}。',
     f'准备阶段：逐文件平台 readelf 和双端 SHA 核对，{len(selection)} 个文件（{sum(r["category"]=="program" for r in selection)} 个程序、{sum(r["category"]=="library" for r in selection)} 个库）由 cross_2013 `prelink -u` 撤销通过；原属性 434/434 可读取，空间门禁通过。证据：{link(HERE/"undo_attempt2.tsv")}、{link(HERE/"metadata.jsonl")}、{link(HERE/"stage_space_gate.json")}。', '',
     '## 排除清单', '', '| 文件 | 原因 |', '| --- | --- |')
 for r in exclusions:add(f'| `{r["path"]}` | `{r["exclusion_reason"]}` |')
 add('', '## 开机与健康门禁', '',
     '出厂镜像原有 failed units 作为基线；后续只拦截**新增** failed units。每次冷启动均以新 boot ID 确认，身份核对见各开机目录。',
     '', '| 状态/开机 | boot ID | 十进程齐全 | 新增 failed unit | 签名拒绝行 | 预链接诊断 | memcheck |',
     '| --- | --- | --- | --- | ---: | --- | --- |')
 for tag,h,d in health:
  b=json.loads((HERE/'boots'/tag/'boot_result.json').read_text())
  diag='；'.join(d['lines'][:2]).replace('|','\\|') or '未输出'
  add(f'| `{tag}` | `{b["boot_id"]}` | {"是" if all(h["processes"].values()) else "否"} | {",".join(h["new_failed_units"]) or "无"} | {h["signature_refusal_lines"]} | `{diag}` | {b["status"]} |')
 add('',f'证据：{link(HERE/"boots/factory_1/health.json")}、各开机目录的 `health.json`、`prelink_diagnostic.json`、`boot_result.json`、完整 dmesg/dlog 与 memcheck 原始目录。', '',
     '## 六次稳定点测量', '',
     '用户态总量与 15 程序组采用 `02_steady/proc_rollup.txt` 的 smaps_rollup `Pss+SwapPss`；库映射采用 `02_steady/smaps_raw.txt.gz` 的逐映射 `Private_Dirty` 或 `Pss`；页表和可用内存来自同一快照 `meminfo.txt`。两种 Pss 来源不混合。15 程序名单来自第三轮 `classification.json` 的 `GCC_nonPIE`。本轮带标记库为 417 个，不能直接当作此前的 410 库。进程在 smaps 和 rollup 间变化时，15 组使用同次 `ps.txt` 的主程序路径补识别；库逐映射统计不能补缺，缺失 PID 单列并限制解释。',
     '', '| 状态/开机 | 全进程 Pss+SwapPss kB | 15 程序组 kB | PageTables kB | MemAvailable kB |',
     '| --- | ---: | ---: | ---: | ---: |')
 for r in boot:
  add(f'| `{r["boot"]}` | {r["Pss_plus_SwapPss_kB"]} | {r["GCC_nonPIE_15_Pss_plus_SwapPss_kB"]} | {r["PageTables_kB"]} | {r["MemAvailable_kB"]} |')
 add('', 'smaps 与 rollup 的进程覆盖差（逐次快照）：')
 for r in boot:
  add(f'- `{r["boot"]}`：`{r["rollup_pids_missing_in_smaps"] or "无"}`。')
 add('', '### 相对出厂的均值差与开机波动', '',
     '差值 = 撤销状态两次均值 − 出厂两次均值；“超出波动”要求差值绝对值严格大于两边各自的两次开机极差，否则记为“无显著差异”。单位 kB。',
     '', '| 指标 | 撤销程序：差/出厂极差/本组极差 | 判定 | 全部撤销：差/出厂极差/本组极差 | 判定 |',
     '| --- | ---: | --- | ---: | --- |')
 metric_names={
  'Pss_plus_SwapPss_kB':'全进程 Pss+SwapPss',
  'GCC_nonPIE_15_Pss_plus_SwapPss_kB':'15 程序组 Pss+SwapPss',
  'PageTables_kB':'PageTables',
  'MemAvailable_kB':'MemAvailable',
  'library_Private_Dirty_15_r--_kB':'带标记库 15 组 r-- Private_Dirty',
  'library_Private_Dirty_15_rw-_kB':'带标记库 15 组 rw- Private_Dirty',
  'library_Private_Dirty_other_r--_kB':'带标记库其他进程 r-- Private_Dirty',
  'library_Private_Dirty_other_rw-_kB':'带标记库其他进程 rw- Private_Dirty',
  'library_rx_Pss_exclusive_ten_kB':'带标记库 r-x Pss：仅 10 程序使用',
  'library_rx_Pss_also_other_or_absent_kB':'带标记库 r-x Pss：也被其他进程使用',
 }
 for metric,name in metric_names.items():
  cells=[]
  for state in STATES[1:]:
   r=changes[state,metric]
   cells.extend([f'{fmt(r["delta_kB"])} / {fmt(r["factory_range_kB"])} / {fmt(r["state_range_kB"])}', '超出波动' if r['larger_than_both_ranges']=='1' else '无显著差异'])
  add(f'| {name} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |')
 add('',f'逐次值、两边均值和极差：{link(HERE/"per_boot_metrics.tsv")}、{link(HERE/"state_deltas.tsv")}；映射明细：{link(HERE/"library_mapping_metrics.tsv")}；库分组与映射进程：{link(HERE/"library_rx_groups.tsv")}。', '',
     '## 13 个对象的加载器相关节驻留', '',
     '每状态只在第一次开机采集 pagemap，故该项**没有两次开机波动**，不判显著性。加载器相关节为 `.dynsym/.dynstr/.gnu.hash/.hash/.gnu.version*/.rel.dyn/.rel.plt`，驻留页按文件偏移和节字节交集分摊。',
     '', '| 对象 | 出厂 kB | 撤销程序 kB | 全部撤销 kB | 撤销程序差 kB | 全部撤销差 kB |',
     '| --- | ---: | ---: | ---: | ---: | ---: |')
 by={}
 for r in pages:by[(r['process'],r['path'],r['boot'])]=float(r['loader_sections_resident_kB'])
 for process,path in sorted({(r['process'],r['path']) for r in pages}):
  a=by.get((process,path,'factory_1'));b=by.get((process,path,'programs_undone_1'));c=by.get((process,path,'all_undone_1'))
  if None in (a,b,c):add(f'| `{process}` `{path}` | 未找到 | 未找到 | 未找到 | 未确定 | 未确定 |')
  else:add(f'| `{process}` `{path}` | {a:.1f} | {b:.1f} | {c:.1f} | {b-a:+.1f} | {c-a:+.1f} |')
 add('',f'证据：{link(HERE/"pagemap13_loader_residency.tsv")}，各状态第一次开机 `pagemap13/collection.json`、逐页原始输出和拉回 ELF。', '',
     '## 与 LLVM 第三轮差额的对照', '',
     '既有跨镜像观测：带预链接库文件映射私有脏页约 +13.9 MiB、15 程序组 Pss+SwapPss 约 +14.8 MiB、只被预链接程序使用的库 r-x Pss 约 +5.4 MiB。它们与本轮 417 库/15 程序组的口径和镜像版本不完全一致，以下只作量级并列，不据此硬凑因果。来源：`memdiff/reports/prelink_group_attribution.md`、`memdiff/reports/weekly_data_table.md`。')
 for metric,name,baseline in [('GCC_nonPIE_15_Pss_plus_SwapPss_kB','15 程序组',14.8*1024),('library_rx_Pss_exclusive_ten_kB','仅 10 程序库 r-x',5.4*1024)]:
  r=changes['all_undone',metric]
  add(f'- {name}：本轮全部撤销 − 出厂 = {fmt(r["delta_kB"])} kB；既有 LLVM − GCC 约 {baseline:,.1f} kB，差额 {float(r["delta_kB"])-baseline:+,.1f} kB。')
 dirty=sum(float(changes['all_undone',m]['delta_kB']) for m in ('library_Private_Dirty_15_r--_kB','library_Private_Dirty_15_rw-_kB','library_Private_Dirty_other_r--_kB','library_Private_Dirty_other_rw-_kB'))
 add(f'- 带标记库 r--+rw- 私有脏页：本轮全部撤销 − 出厂 = {dirty:,.1f} kB；既有 LLVM − GCC 约 {13.9*1024:,.1f} kB，差额 {dirty-13.9*1024:+,.1f} kB。', '',
     '## 恢复和剩余限制', '',
     f'恢复前已逐文件核对原版 SHA、属主、权限、全部 xattr、getcap、chsmack：{link(HERE/"recovery/original_verify.json")}。恢复重启健康门禁={recovery["health"]["healthy"]}，预链接诊断恢复为 `prelink checking: ok`={recovery["prelink_diag"]["has_ok"]}，暂存目录与工具目录已清理，sdb root off 并确认 UID 5001。证据：{link(HERE/"recovery/recovery_result.json")}。',
     'overlay 上层目录残留与原版字节一致的副本；重刷镜像可完全清理。恢复前后上层文件清单：'+link(HERE/'recovery/overlay_before_recovery_reboot.stdout')+'、'+link(HERE/'recovery/overlay_after_recovery_reboot.stdout')+'。',
     '本实验不能消除同镜像开机噪声；只有超出两边极差的指标才列为可辨差异。13 对象 pagemap 只有一次/状态，不具有重复运行波动证据。', '',
     '## 上次尝试的停止记录（原文保留）', '', old)
 REPORT.write_text('\n'.join(report).rstrip()+'\n')
 p.log('REPORT DONE '+str(REPORT))

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
