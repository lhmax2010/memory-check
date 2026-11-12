#!/usr/bin/env python3
"""Classify current LLVM defined WEAK exports; no GCC comparison is used."""
import csv,datetime,gzip,json,os,subprocess
from collections import Counter,defaultdict
from pathlib import Path

OUT=Path(__file__).resolve().parent
SRC=OUT.parent/'system_code_page_sections'
FILT=Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-c++filt')
LIB=FILT.parent.parent/'lib64'
def log(msg):
 line=f'{datetime.datetime.now().astimezone().isoformat()} {msg}'
 with (OUT/'progress.log').open('a') as f:f.write(line+'\n')
 print(line,flush=True)
def cat(raw,dem):
 if raw.startswith(('_ZTV','_ZTI','_ZTS','_ZTT')) or dem.startswith(('vtable for ','typeinfo for ','typeinfo name for ','VTT for ')):return 'vtable_typeinfo'
 if '<' in dem and '>' in dem:return 'template_instance_candidate'
 if '::' in dem and '(' in dem:return 'class_member_inline_unverified'
 return 'other'
def main():
 src=SRC/'dynsym_symbols.tsv.gz';records=[]
 with gzip.open(src,'rt') as f:
  for r in csv.DictReader(f,delimiter='\t'):
   if r['image']=='LLVM' and r['bind']=='WEAK' and r['ndx']!='UND' and r['name'] and r['visibility'] in ('DEFAULT','PROTECTED'):
    records.append({'path':r['path'],'name':r['name']})
 log(f'WEAK records {len(records)}')
 unique=sorted({r['name'] for r in records});decoded={}
 for i in range(0,len(unique),3000):
  chunk=unique[i:i+3000]
  res=subprocess.run([str(FILT)],input='\n'.join(chunk)+'\n',text=True,capture_output=True,
                     stdin=subprocess.DEVNULL if False else None,
                     env={**os.environ,'LD_LIBRARY_PATH':str(LIB)},timeout=120)
  if res.returncode or len(res.stdout.splitlines())!=len(chunk):raise RuntimeError(f'c++filt batch {i} rc={res.returncode} {res.stderr[:300]}')
  decoded.update(zip(chunk,res.stdout.splitlines()))
  if i%15000==0:log(f'c++filt {min(i+3000,len(unique))}/{len(unique)}')
 count=Counter();byfile=defaultdict(Counter);inline_bytes=0;inline_count=0
 with gzip.open(OUT/'weak_symbols_classified.tsv.gz','wt',newline='') as f:
  w=csv.DictWriter(f,['path','name','demangled','category','class_member_inline_candidate'],delimiter='\t',lineterminator='\n');w.writeheader()
  for r in records:
   dem=decoded[r['name']];kind=cat(r['name'],dem);count[kind]+=1;byfile[r['path']][kind]+=1
   inline_candidate=('::' in dem and '(' in dem)
   if inline_candidate:
    inline_count+=1
    inline_bytes+=22+len(r['name'].encode())+1
   w.writerow({'path':r['path'],'name':r['name'],'demangled':dem,'category':kind,
               'class_member_inline_candidate':int(inline_candidate)})
 with (OUT/'weak_category_by_file.tsv').open('w',newline='') as f:
  fields=['path','vtable_typeinfo','template_instance_candidate','class_member_inline_unverified','other','total']
  w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader()
  for path,c in sorted(byfile.items()):w.writerow({'path':path,**{k:c[k] for k in fields[1:-1]},'total':sum(c.values())})
 with (OUT/'elf_metrics.tsv').open() as f:metrics=list(csv.DictReader(f,delimiter='\t'))
 with (OUT/'relocation_summary.json').open() as f:rel=json.load(f)
 summary={'defined_WEAK_export_count':len(records),'category_counts':dict(count),
  'class_member_inline_candidates':inline_count,
  'structural_bytes_ceiling_22_plus_name':inline_bytes,'structural_bytes_ceiling_kB':inline_bytes/1024,
  'candidate_rule':'WEAK DEFAULT/PROTECTED defined LLVM symbols; class member method name; inline status unverified',
  'Bsymbolic_function_candidate_relocations':rel['Bsymbolic_function_candidate_relocs'],
  'Bsymbolic_function_candidate_total':sum(rel['Bsymbolic_function_candidate_relocs'].values()),
  'as_needed_removable_mapping_count':'未确定',
  'all_NEEDED_edges_for_mapped_ELF':sum(int(r['DT_NEEDED_count']) for r in metrics if int(r['mapped_processes'])>0)}
 (OUT/'symbol_estimates.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 log('WEAK DONE')
if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';log('ERROR '+repr(e));raise
 finally:print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态='+status,flush=True)
