#!/usr/bin/env python3
"""Derive reproducible LLVM-only summary bounds from primary tables."""
import csv,datetime,json,statistics
from collections import Counter,defaultdict
from pathlib import Path

O=Path(__file__).resolve().parent
S=O.parent/'system_code_page_sections'
def table(path):
 with path.open(newline='') as f:yield from csv.DictReader(f,delimiter='\t')
def save(name,obj):(O/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def write(name,records,fields=None):
 records=list(records);fields=fields or list(records[0])
 with (O/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(records)
def log(msg):
 line=datetime.datetime.now().astimezone().isoformat()+' '+msg
 with (O/'progress.log').open('a') as f:f.write(line+'\n')
 print(line,flush=True)
def main():
 metrics={r['path']:r for r in table(O/'elf_metrics.tsv')}
 pages=list(table(O/'relocation_pages.tsv'))
 files=list(table(O/'code_file_pss.tsv'))
 model=list(table(O/'relocation_model_by_file.tsv'))
 section_pss=Counter()
 resident=defaultdict(Counter)
 for r in table(S/'section_residency.tsv'):
  resident[r['path']][r['section']]+=float(r['resident_kB'])
 pss={r['path']:float(r['rx_Pss_kB']) for r in files}
 for path,ss in resident.items():
  den=sum(ss.values())
  if den and path in pss:
   for name,n in ss.items():section_pss[name]+=n/den*pss[path]
 page_total=Counter();exclusives=Counter()
 for r in pages:
  path=r['path'];metric=metrics[path];weight=int(r['weighted_kB']);n=int(r['target_count'])
  if not path.endswith('.so') and '.so.' not in path:continue
  cats=set(r['container_classes'].split(';'))
  if 'vtable' in cats:page_total['vtable_upper_kB']+=weight
  if 'typeinfo' in cats:page_total['typeinfo_upper_kB']+=weight
  if {'vtable','typeinfo'}<=cats:page_total['both_vtable_typeinfo_kB']+=weight
  if cats=={'vtable'}:page_total['only_vtable_container_kB']+=weight
  if cats=={'typeinfo'}:page_total['only_typeinfo_container_kB']+=weight
  if 'unknown' in cats:page_total['unknown_container_page_kB']+=weight
  if n*4<256:page_total['lt256_target_bytes_kB']+=weight
  if r['types']=='JUMP_SLOT':
   if int(metric['BIND_NOW']):page_total['now_jump_only_page_kB']+=weight
   else:page_total['lazy_jump_only_page_kB']+=weight
  if r['sections']=='.data.rel.ro':page_total['data_rel_ro_page_kB']+=weight
  page_total['all_library_page_kB']+=weight
 small=list(table(O/'small_library_top50.tsv'))
 allsmall=[r for r in model if r['is_library']=='1' and int(r['mapped_processes'])>0 and 1<=int(r['writable_relocation_pages'])<=2]
 page_total['small_library_1to2_page_kB']=sum(int(r['predicted_file_dirty_kB']) for r in allsmall)
 page_total['small_library_1to2_files']=len(allsmall)
 bind_all=Counter();bind_mapped=Counter();bind_with_plt=Counter()
 for r in metrics.values():
  tag='NOW' if int(r['BIND_NOW']) else 'lazy_or_unspecified'
  bind_all[tag]+=1
  if int(r['mapped_processes']):
   bind_mapped[tag]+=1
   if int(r['reloc_JUMP_SLOT']):bind_with_plt[tag]+=1
 top_loader=sorted(files,key=lambda r:-float(r['loader_unique_kB']))[:50]
 write('loader_residency_top50.tsv',top_loader)
 weak=json.loads((O/'symbol_estimates.json').read_text())
 budget=json.loads((O/'smaps_budget.json').read_text())
 code=json.loads((O/'code_budget.json').read_text())
 total=budget['budget_kB']['Pss_total']
 if abs(sum(v for k,v in budget['budget_kB'].items() if k not in ('Pss_total','SwapPss','code_rx'))+budget['budget_kB']['code_rx']-total)>1e-6:
  raise RuntimeError('PSS categories do not sum to PSS total')
 if abs(sum(code['classified_Pss_kB'].values())-budget['budget_kB']['code_rx'])>0.01:
  raise RuntimeError('code categories do not sum to r-x PSS')
 rel=json.loads((O/'relocation_summary.json').read_text())
 if rel['readelf_errors']:raise RuntimeError('readelf errors')
 state=json.loads((S/'collection.json').read_text())
 mem=S/'raw/snapshot_meminfo.stdout'
 match=__import__('re').search(r'^PageTables:\s+(\d+)\s+kB',mem.read_text(),__import__('re').MULTILINE) if mem.exists() else None
 data={'image_BUILD_ID':state.get('build_id',''),
  'snapshot_date':state.get('started_utc','')[:10], 'measured_user_processes':budget['user_processes_with_smaps'],
  'smaps_processes_including_kernel_threads':budget['complete_processes'],
  'exited_or_incomplete_processes':budget['missing_or_exited'],'Pss_total_kB':total,
  'SwapPss_total_kB':budget['budget_kB']['SwapPss'],
  'Pss_plus_SwapPss_kB':total+budget['budget_kB']['SwapPss'],
  'budget_Pss_kB':{**{k:v for k,v in budget['budget_kB'].items() if k not in ('Pss_total','SwapPss','code_rx')},
                   **{'code_'+k:v for k,v in code['classified_Pss_kB'].items()}},
  'PageTables_same_snapshot_kB':int(match[1]) if match else '未找到',
  'VMA_distribution':budget['VMA_distribution'],'mapped_libraries_distribution':budget['library_distribution'],
  'section_Pss_kB':dict(section_pss),'relocation_page_bounds':dict(page_total),
  'BIND_NOW_all_ELF':dict(bind_all),'BIND_NOW_mapped_ELF':dict(bind_mapped),
  'BIND_NOW_mapped_ELF_with_JUMP_SLOT':dict(bind_with_plt),
  'WEAK_export_categories':weak['category_counts']}
 save('derived_summary.json',data)
 # A compact, auditable file-by-file static upper for loader table resident PSS.
 log('DERIVED DONE')
if __name__=='__main__':
 state='成功'
 try:main()
 except BaseException as e:state='失败';log('ERROR '+repr(e));raise
 finally:print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态='+state,flush=True)
