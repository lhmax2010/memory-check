#!/usr/bin/env python3
"""Summarize the two completed factory-state boots only."""
import csv,json
from collections import Counter
import analyze_ab as a
import preflight as p

HERE=p.HERE

def main():
 c=json.loads((a.M/'data/llvm_round3/analysis/classification.json').read_text())
 nonpie=set(c['GCC_nonPIE'])
 libraries={r['path'] for r in csv.DictReader((HERE/'pull_classify.tsv').open(),delimiter='\t') if r['selected']=='1' and r['category']=='library'}
 ten={r['path'] for r in csv.DictReader((a.M/'data/prelink_group_attribution/gnu_liblist_executables.tsv').open(),delimiter='\t')}
 base=[];mappers={};rx_by={}
 for tag in ('factory_1','factory_2'):
  steady=a.snapshot(tag)
  proc,raw,mapper=a.parse_smaps(steady/'smaps_raw.txt.gz',libraries,nonpie,ten)
  total,group,_,missing=a.rollup(steady/'proc_rollup.txt',proc,nonpie,steady/'ps.txt')
  d=Counter();rx=Counter()
  for (pid,exe,path,seg),metric in raw:
   val=raw[(pid,exe,path,seg),metric]
   if metric=='Private_Dirty':d['15' if exe in nonpie else 'other',seg]+=val
   if metric=='Pss':rx[path]+=val
  mappers[tag]=mapper;rx_by[tag]=rx
  mem=a.meminfo(steady/'meminfo.txt')
  row={'boot':tag,'Pss_plus_SwapPss_kB':total,'GCC_nonPIE_15_Pss_plus_SwapPss_kB':group,'PageTables_kB':mem['PageTables'],'MemAvailable_kB':mem['MemAvailable'],'rollup_pids_missing_in_smaps':';'.join(missing)}
  for who in ('15','other'):
   for seg in ('r--','rw-'):row[f'library_Private_Dirty_{who}_{seg}_kB']=d[who,seg]
  base.append(row)
  p.log('FACTORY '+tag+' userspace='+str(total)+' 15group='+str(group))
 for row in base:
  rx=rx_by[row['boot']]
  exclusive=[];shared=[]
  for path in libraries:
   exes=mappers['factory_1'].get(path,set())|mappers['factory_2'].get(path,set())
   if exes and exes<=ten:exclusive.append(path)
   else:shared.append(path)
  row['library_rx_Pss_exclusive_ten_kB']=sum(rx[path] for path in exclusive)
  row['library_rx_Pss_also_other_or_absent_kB']=sum(rx[path] for path in shared)
 a.tsv(HERE/'factory_baseline_metrics.tsv',base)
 noise=[]
 for k in base[0]:
  if k.endswith('_kB'):
   v1=float(base[0][k]);v2=float(base[1][k])
   noise.append({'metric':k,'factory_1_kB':v1,'factory_2_kB':v2,'mean_kB':(v1+v2)/2,'range_kB':abs(v1-v2)})
 a.tsv(HERE/'factory_baseline_noise.tsv',noise)
 pages=a.pagemap13('factory_1')
 a.tsv(HERE/'factory1_pagemap13_loader_residency.tsv',pages,['boot','process','path','rx_present_kB','loader_sections_resident_kB'])
 p.log('FACTORY SUMMARY DONE')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
