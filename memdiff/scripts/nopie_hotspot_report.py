#!/usr/bin/env python3
"""Render reproducible evidence tables from nopie_memory_hotspots outputs."""
from __future__ import annotations
import argparse,csv,json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from datetime import datetime

ROOT=Path(__file__).resolve().parents[2]
CAT=('file_exec','file_readonly','file_writable','file_other','stack','anonymous','special')
LABEL={'file_exec':'文件执行','file_readonly':'文件只读','file_writable':'文件可写',
       'file_other':'文件其他','stack':'可识别栈','anonymous':'其他匿名','special':'特殊映射'}
def R(p):
 with p.open(newline='') as f:return list(csv.DictReader(f,delimiter='\t'))
def D(s):return Decimal(str(s))
def f(x):return f'{D(x):,.1f}' if D(x)%1 else f'{D(x):,}'
def link(name):return f'[数据](../data/noPIE_memory_hotspot_analysis/{name})'
def md_table(lines,headers,rows):
 lines.extend(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |'])
 lines.extend('| '+' | '.join(str(v).replace('|','\\|') for v in r)+' |' for r in rows)
 lines.append('')

def run(out,report):
 cproc=R(out/'C_processes_six.tsv');pc=R(out/'C_process_comparisons.tsv')
 files=R(out/'C_file_comparisons.tsv');aud=R(out/'argot_capture_audit.tsv')
 argot=R(out/'argot_processes_six.tsv');elf=R(out/'static_elf_evidence.tsv')
 validation=json.loads((out/'validation.json').read_text());checks=validation['checks']
 lines=['# noPIE 新镜像剩余内存开销：固定 94 身份的离线定位','',
  '## 结论与边界','',
  '六次快照和固定 94 个 `(comm, exe)` 身份完全沿用 [整体差值核对](noPIE_memory_delta_reconciliation.md) 的输入与规则。'+
  '本轮每次仅汇总已成功读取的 94 个进程；所有值为逐映射 **Pss+SwapPss，单位 KiB**。'+
  '相对 GCC，C 均值仍减少 20,183 KiB；相对第三轮 LLVM 减少 26,145 KiB。'+
  '以下正增量是下降总量内部的抵消项，不能互相相加为可回收量。'+
  '两次启动仅用于观察区间是否分离，不作统计显著性判断。新镜像同时改变 noPIE、LTO、MLGO 等条件，单项因果未确定。', '',
  '六次输入的 SHA256 在运行时与 [上一轮输入清单](../data/noPIE_memory_delta_reconciliation/inputs.tsv) 逐项核对；'+
  f'本轮 {link("validation.json")} 记录 manifest 和固定清单哈希。旧 LLVM 对照是第三轮两次开机，没有混入 11 月 11 日单次数据。'+
  'noPIE BUILD_ID 为 `T-KSU2EJAKUC-0101-PERF-202611120549`。原始快照、boot ID、采样时间和稳定标记见'+
  '[输入 manifest](../data/noPIE_memory_delta_reconciliation/input_manifest.json) 与[原报告](noPIE_memory_delta_reconciliation.md)。', '',
  '### 分类定义','',
  '- `file_exec`：文件路径且映射权限含 `x`；`file_readonly`：文件路径、无 `x`、有 `r`、无 `w`；`file_writable`：文件路径且有 `w`。'+
  '其余文件映射保留 `file_other`。不跨镜像按虚拟地址配对。',
  '- `stack` 只认明确的 `[stack]`/`[stack:<tid>]` 等标签；`[heap]`、`[anon]`、`[anon:...]` 和无路径映射归 `anonymous`。'+
  '未标注 worker 栈无法识别，仍留在匿名类。',
  '- `/dev/`、`/proc/`、`/sys/`、`/kdbus-`、memfd 和其他内核特殊标签归 `special`；路径带 `(deleted)` 保留字面值，绝不与未删除路径合并。'+
  '每条 VMA 恰好进入一个主类。Private_Dirty、Rss、Shared_Clean 只作辅助诊断，不加入 Pss+SwapPss 总和。', '',
  '## 六次 C 总量及映射主类','']
 pr=defaultdict(list)
 for x in cproc:pr[x['boot']].append(x)
 rows=[]
 for b in ('GCC1','GCC2','LLVM31','LLVM32','noPIE1','noPIE2'):
  ps=sum(D(x['Pss_kB']) for x in pr[b]);sw=sum(D(x['SwapPss_kB']) for x in pr[b]);co=checks[b]
  rows.append([b,len(pr[b]),f(ps),f(sw),f(co['C_kB'])]+[f(co['categories_kB'][c]) for c in CAT])
 md_table(lines,['快照','身份实例','Pss','SwapPss','合计']+[LABEL[c] for c in CAT],rows)
 lines += [f'逐进程六次值及各类别见 {link("C_processes_six.tsv")}；逐 VMA 分类见 {link("classified_vmas.tsv.gz")}。', '',
           '## A. 正增量进程与文件','',
           '表内新旧两次值按同一镜像并列；均值差是新镜像均值减基线均值，区间分离表示两次新值均高于两次旧值。'+
  '文件级 0 表示在对应完整 C 快照未映射，不表示文件不存在；`*_present` 列保留这一区别。'+
  '完整正负进程与文件差分见 '+link('C_process_comparisons.tsv')+'、'+link('C_file_comparisons.tsv')+'，'+
           '前 20 正项另见 '+link('top20_process_positive.tsv')+'、'+link('top20_file_positive.tsv')+'。', '']
 for base in ('GCC','LLVM3'):
  key='noPIE_minus_'+base
  lines += [f'### noPIE − {base}：正增量进程','']
  positives=sorted((x for x in pc if x['comparison']==key and D(x['delta_total_kB'])>0),key=lambda x:-D(x['delta_total_kB']))
  rows=[]
  for x in positives[:10]:
   parts=sorted(((c,D(x['delta_'+c+'_total_kB'])) for c in CAT),key=lambda t:-abs(t[1]))
   major=', '.join(f'{LABEL[c]} {f(v):s}' for c,v in parts if abs(v)>=40) or '各类均 <40'
   rows.append([x['identity_key'],f(x['base1_total_kB'])+'/'+f(x['base2_total_kB']),
    f(x['new1_total_kB'])+'/'+f(x['new2_total_kB']),f(x['delta_total_kB']),
    f(x['delta_Pss_kB'])+'/'+f(x['delta_SwapPss_kB']),x['interval'],major])
  md_table(lines,['身份','旧 1/2','新 1/2','Δ合计','ΔPss/Swap','区间','主要类别净变化'],rows)
  lines += [f'### noPIE − {base}：正增量文件（仅 C 内映射）','']
  positives=sorted((x for x in files if x['comparison']==key and D(x['delta_total_kB'])>0),key=lambda x:-D(x['delta_total_kB']))
  rows=[]
  for x in positives[:10]:
   cats=sorted(((c,D(x['delta_'+c+'_total_kB'])) for c in CAT if c.startswith('file_')),key=lambda t:-abs(t[1]))
   major=', '.join(f'{LABEL[c]} {f(v)}' for c,v in cats if abs(v)>=40) or '各类均 <40'
   old_users=f'{x[base+"1_users_C"]}/{x[base+"2_users_C"]}'
   new_users=f'{x["noPIE1_users_C"]}/{x["noPIE2_users_C"]}'
   rows.append([x['path'],f(x['base1_total_kB'])+'/'+f(x['base2_total_kB']),
    f(x['new1_total_kB'])+'/'+f(x['new2_total_kB']),f(x['delta_total_kB']),
    f(x['delta_Pss_kB'])+'/'+f(x['delta_SwapPss_kB']),x['interval'],old_users+'→'+new_users,major])
  md_table(lines,['文件路径','旧 1/2','新 1/2','Δ合计','ΔPss/Swap','区间','C 使用者','主要映射变化'],rows)
 lines += ['### 重点对象的证据解释','',
  '1. **`enlightenment`** 相对 LLVM3 为 +3,773.5 KiB，但观察区间重叠。其特殊映射净增 +4,050 KiB，'+
  '来自 `/dev/dri/card0`：LLVM3 两次为 8,100/0 KiB，noPIE 为 8,100/8,100 KiB。'+
  '同一对象的文件执行映射反而 −230.5 KiB；noPIE `.text` 为 1,022,500 B，LLVM3 为 1,029,676 B。'+
  '这首先是 GPU 映射/状态可比性问题，不能称作代码增长。'+link('classified_vmas.tsv.gz')+'、'+link('static_elf_evidence.tsv')+'。',
  '2. **`libpisa-ipc.so`** 的 C 内文件 Pss+SwapPss 相对 GCC 为 +458 KiB，5/5 与 5/5 个 C 身份映射，'+
  '全部来自执行映射；GCC/noPIE `.text` 为 479,996/885,568 B。静态大小变化与映射增量同向，'+
  '但版本/源码/编译参数尚未配齐，不能直接归因 LTO 或编译器。'+link('C_file_comparisons.tsv')+'、'+link('static_elf_evidence.tsv')+'。',
  '3. **`libvorbisenc.so.2.0.12`** 相对 GCC 为 +819 KiB，其中文件只读 +728 KiB；GCC 两次固定 C 均未映射该路径，'+
  '因此从映射文件拉回的 GCC ELF 副本也未取得，无法核对静态版本。这首先是加载/依赖集合差异，'+
  '不是同一文件的内存增长。LLVM3 与 noPIE 均有 ELF 副本，noPIE 相对 LLVM3 实际 −186 KiB。'+link('C_file_comparisons.tsv')+'、'+link('static_elf_evidence.tsv')+'。',
  '4. **`avocd`** 相对 GCC 进程合计 +259 KiB，其中 Pss −83、SwapPss +342；自身文件 +312 KiB，'+
  '其执行映射 +314 KiB。GCC/noPIE `.text` 为 662,936/1,276,590 B，静态差距明显，'+
  '但进程合计受其他映射和换出抵消。'+link('C_process_comparisons.tsv')+'、'+link('static_elf_evidence.tsv')+'。',
  '5. **`TA_native-home` / `team-launcher`** 相对 GCC 进程 +1,325.5 KiB，但区间重叠；'+
  '文件执行映射 +1,349 KiB、可识别栈 −436 KiB。主程序 `.text` noPIE 仅 572 B，'+
  '因此不能把 +1,349 KiB 归到主程序代码；需先拆其加载文件和同场景工作量。'+link('C_process_comparisons.tsv')+'、'+link('static_elf_evidence.tsv')+'。', '',
  '### 前 10 个 ELF 的静态核查','',
  '按每个对象在进程或文件视角的**较大正差值**排序选 10 个，不把两种视角相加。'+
  '原始平台交叉 readelf 节表、程序头、动态段和 note 已压缩保存在数据目录；工具路径和 SHA256 见 '+link('static_tool.json')+'。'+
  '下表 `.text` 为文件节大小（B），不是驻留 Pss。缺副本写未取得，不解释为映射值 0。', '']
 rows=[]
 for rank in range(1,11):
  a={x['image']:x for x in elf if int(x['rank'])==rank}
  rr=a['noPIE'];
  def cell(image):
   x=a[image]
   return '未取得' if x['available']=='0' else f"{x.get('ELF_type','?')}; .text {x.get('.text_bytes','?')}; {x.get('build_id','?')[:10]}"
  rows.append([rank,rr['path'],cell('GCC'),cell('LLVM3'),cell('noPIE'),rr['in_original_410']])
 md_table(lines,['序','路径','GCC ELF/.text/Build ID 前缀','LLVM3','noPIE','原 410 库'],rows)
 lines += ['同路径三侧哈希和 Build ID 多数不同，只能证明副本字节不相同；没有对应包版本和同源码构建记录时，'+
  '“同版本”与“编译器造成”均未确定。`.comment` 为局部编译痕迹，不能覆盖整个包。'+
  'PT_LOAD 权限、文件/内存大小与对齐、`.rodata/.dynsym/.dynstr` 和重定位节大小详见 '+link('static_elf_evidence.tsv')+'。'+
  '本轮没有逐页节归属数据，不能把 r-x Pss 精确分给 `.text` 或 `.dynsym`。', '',
  '## B. argot 路径族的可比性','',
  '新镜像两次都测到三条路径；GCC 和 LLVM3 四次旧快照的**已测台账**均无同身份记录，'+
  '但这不能证明旧镜像从未安装/启动，也不能给出三者的同程序增长率。'+
  'noPIE 两次各有 6 个采集中退出、未获得完整身份和内存的 PID，未测部分未估算。'+
  '同次 `/proc/<pid>/status` 的 PPid 证明两次均有 `systemd→tsr→tsr-bwrap→tsr→argot` 链；'+
  '这是父子关系事实，是否属于测试污染/预期业务仍未确定。'+link('argot_capture_audit.tsv')+'。', '']
 rows=[]
 for exe in sorted(set(x['exe'] for x in aud)):
  x=[z for z in aud if z['exe']==exe]
  one=[z for z in x if z['boot']=='noPIE1'][0];two=[z for z in x if z['boot']=='noPIE2'][0]
  rows.append([exe,one['instances']+'/'+two['instances'],one['Pss_kB']+'/'+two['Pss_kB'],
   one['SwapPss_kB']+'/'+two['SwapPss_kB'],one['total_kB']+'/'+two['total_kB'],
   '旧四次不在已测台账；同程序比较不可用'])
 md_table(lines,['路径','新实例 1/2','Pss 1/2','Swap 1/2','合计 1/2','可比性'],rows)
 lines += ['三者在 noPIE 第一次合计 **13,172 KiB**、第二次 **13,144 KiB**；上一轮报告的 13,158 KiB 是两次均值：'+
  '`argot` 12,026 + `tsr` 968 + `tsr-bwrap` 164。'+
  '这解释了 R 净差 +13,364 KiB 的 98.46%，但只是一侧测得的进程集合/运行状态贡献，**不是同程序内存回退**。'+
  '当前 `argot` 可执行副本 `.comment` 含 Tizen GCC、Ubuntu GCC 与 rustc 1.94.0 标记，'+
  '其 10,059,108 B `.text` 和相关静态节见 '+link('static_elf_evidence.tsv')+'；'+
  '这不足以推断包是否完整迁移到 clang、是否使用 LTO，旧两镜像没有可配对副本。', '',
  '三者均归“**当前高占用但历史不可比；需要服务/镜像配置证据**”。现有父子链支持它们作为同一运行树，'+
  '不支持将三者每项视为独立优化收益。未来先核对镜像包清单、启动单元/工作负载与采样时刻，再决定是否进入同程序优化实验。', '',
  '## 候选清单与最小验证','',
  '下列排序综合正增量、两次区间、同对象可比性和可验证性；“验证”不代表本轮实施，也不承诺节省量。'+
  '进程与其映射文件会重叠，候选增量不得累加。完整候选字段见 '+link('candidates.tsv')+'。', '']
 specs=[
  ('P1','文件','/usr/lib/libpisa-ipc.so','GCC','先核实同源码包/版本与构建参数，再在同版本受控构建中量 .text 与 r-x Pss','先补构建证据；不能直接实验'),
  ('P1','进程','enlightenment | /usr/bin/enlightenment','LLVM3','先在同 GPU 状态、同 uptime 下复测 /dev/dri/card0 Pss，区分 0/8100 KiB 状态','先补状态可比性'),
  ('P1','进程族','argot+tsr+tsr-bwrap','LLVM3','先核对三版包/服务启用与父子链、相同工作负载；再决定是否比较同程序','先补历史可比性'),
  ('P2','文件','/usr/lib/libvorbisenc.so.2.0.12','GCC','先核对 GCC 未在固定 C 映射的原因与两侧依赖集合；另找 GCC 包版本','先补加载/文件证据'),
  ('P2','文件','/usr/bin/avocd','GCC','核对同源码/版本与 ELF 配置，复测 r-x Pss 和 SwapPss；再考虑构建实验','先补版本证据'),
  ('P2','进程','launchpad-loade | /usr/bin/launchpad-loader','GCC','核对两次依赖集合、文件只读页和匿名分配；同负载复测','先补映射证据'),
  ('P3','进程','TA_native-home | /usr/bin/team-launcher','GCC','固定启动场景与线程数，逐文件核对执行映射及栈变化','先补工作负载证据'),
  ('P3','文件','/opt/usr/apps/com.samsung.tv.ContentsBrowser/shared/res/libcompcb.so','GCC','核对同源码包/版本与构建选项，复测该文件的 r-x Pss','先补版本证据'),
  ('P3','文件','/usr/lib/libsecurity-manager-commons.so.1.0.2','LLVM3','同 uptime 复测该文件 SwapPss、进程数和可写映射；先排除换出状态','先补换出可比性'),
 ]
 cand=[]
 for pri,kind,obj,base,action,gate in specs:
  if kind=='进程族':
   cand.append(dict(priority=pri,kind=kind,object=obj,comparison='noPIE_minus_'+base,
    base1_kB='not_measured',base2_kB='not_measured',new1_kB=13172,new2_kB=13144,
    delta_mean_kB='not_comparable',interval='insufficient',main_category='argot file_exec about 6.3 MiB; 3.4 MiB SwapPss',
    comparability='old same identity unavailable',next_minimum_action=action,gate=gate))
   continue
  r=next(x for x in (pc if kind=='进程' else files) if x['comparison']=='noPIE_minus_'+base and x.get('identity_key',x.get('path'))==obj)
  cats=CAT if kind=='进程' else [c for c in CAT if c.startswith('file_')]
  largest=max(cats,key=lambda c:abs(D(r['delta_'+c+'_total_kB'])))
  cand.append(dict(priority=pri,kind=kind,object=obj,comparison='noPIE_minus_'+base,
   base1_kB=r['base1_total_kB'],base2_kB=r['base2_total_kB'],new1_kB=r['new1_total_kB'],new2_kB=r['new2_total_kB'],
   delta_mean_kB=r['delta_total_kB'],delta_Pss_kB=r['delta_Pss_kB'],delta_SwapPss_kB=r['delta_SwapPss_kB'],
   interval=r['interval'],main_category=f'{largest} {r["delta_"+largest+"_total_kB"]} KiB',
   comparability='same identity/path observed; source version not established' if kind=='文件' else
                 'same identity observed; workload may differ',next_minimum_action=action,gate=gate))
 fields=list(dict.fromkeys(k for x in cand for k in x))
 with (out/'candidates.tsv').open('w',newline='') as f0:
  w=csv.DictWriter(f0,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(cand)
 md_table(lines,['优先级','对象','对照','旧 1/2','新 1/2','均值差','区间','下一步'],
  [[x['priority'],x['object'],x['comparison'].removeprefix('noPIE_minus_'),
    str(x['base1_kB'])+'/'+str(x['base2_kB']),str(x['new1_kB'])+'/'+str(x['new2_kB']),
    x['delta_mean_kB'],x['interval'],x['next_minimum_action']] for x in cand])
 lines += ['## 校验、覆盖和需要修正的表述','',
  '所有 6 次固定 94 身份 C 与上一轮 `six_snapshots.tsv` **逐次 0 KiB 差**；'+
  '逐进程主类之和、94 身份合计、文件映射总和对文件主类之和均为 **0 KiB 误差**。'+
  '从身份差分重算 ΔC：noPIE−GCC −20,183 KiB，noPIE−LLVM3 −26,145 KiB，'+
  '与 [上一轮比较表](../data/noPIE_memory_delta_reconciliation/comparisons.tsv) 相同。'+
  f'实际分类 VMA {validation["classified_VMA_rows"]:,} 条，其中固定 C {sum(v["VMA_count_C"] for v in checks.values()):,} 条、argot 路径族 '+
  f'{validation["classified_VMA_rows"]-sum(v["VMA_count_C"] for v in checks.values()):,} 条；六次共 564 个固定 C 进程实例。'+link('validation.json')+'。', '',
  '本轮仅对固定 C 和 argot 三路径族逐 VMA 重读；不声称覆盖 T 中其他 R 的映射。'+
  'noPIE 两次各 6 个采集时退出/不完整 PID 无法计入已采集总量；旧镜像约 45 分钟采样而新镜像约 13 分钟，'+
  'GPU、Swap 和应用工作量可能变化。文件级按路径配对，不把不同路径/版本自动认作同一二进制。'+
  '同一快照同路径的文件映射还核对 device/inode；若出现多个 inode，脚本停止，不静默合并。'+
  'GCC 的 `libvorbisenc` 文件副本未取得；多处包版本/同源码记录缺失。'+
  '脚本不读终端输入，运行日志与结束状态见 '+link('run_console.log')+'、'+link('static_console.log')+'。', '',
  '旧报告数值无需更正；需要避免把 `argot` 路径族 +13,158 KiB 表述为“同程序回退”或“新服务已证实”，'+
  '以及把 `enlightenment` 的 GPU 特殊映射差额表述为 `.text` 增长。', '',
  '## 复现','',
  '```bash','ulimit -v 2500000',
  'taskset -c 0 nice -n 19 ionice -c3 python3 memdiff/scripts/nopie_memory_hotspots.py --manifest memdiff/data/noPIE_memory_delta_reconciliation/input_manifest.json --out memdiff/data/noPIE_memory_hotspot_analysis',
  'taskset -c 0 nice -n 19 ionice -c3 python3 memdiff/scripts/nopie_hotspot_static.py --out memdiff/data/noPIE_memory_hotspot_analysis',
  'taskset -c 0 nice -n 19 ionice -c3 python3 memdiff/scripts/nopie_hotspot_report.py --out memdiff/data/noPIE_memory_hotspot_analysis --report memdiff/reports/noPIE_memory_hotspot_analysis.md',
  'taskset -c 0 nice -n 19 ionice -c3 python3 -m unittest memdiff.tests.test_nopie_memory_hotspots','```','']
 report.write_text('\n'.join(lines))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();state='成功'
 try:run(a.out,a.report)
 except Exception:state='失败';raise
 finally:print('已结束',datetime.now().astimezone().isoformat(),'状态='+state,flush=True)
