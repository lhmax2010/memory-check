#!/usr/bin/env python3
"""Conservative .data.rel.ro target-container classification on LLVM ELF copies."""
import csv,datetime,gzip,json,struct
from collections import Counter,defaultdict
from pathlib import Path

O=Path(__file__).resolve().parent
ROOT=O.parent/'system_code_page_sections/elf'
def log(msg):
 line=datetime.datetime.now().astimezone().isoformat()+' '+msg
 with (O/'progress.log').open('a') as f:f.write(line+'\n')
 print(line,flush=True)
def rows(path):
 with path.open() as f:yield from csv.DictReader(f,delimiter='\t')
def section_for(sections,addr):
 xs=[s for s in sections if 'A' in s['flags'] and s['vaddr']<=addr<s['vaddr']+s['size']]
 return min(xs,key=lambda s:s['size']) if xs else None
def main():
 byfile=defaultdict(list)
 for r in rows(O/'elf_sections_vaddr.tsv'):
  if r['size_bytes'] and int(r['size_bytes'])>0:
   byfile[r['path']].append({'name':r['section'],'vaddr':int(r['vaddr']),'size':int(r['size_bytes']),
                            'fileoff':int(r['file_offset']),'flags':r['flags'],'type':r['type']})
 metrics={r['path']:r for r in rows(O/'elf_metrics.tsv')}
 counts=Counter();page_classes=defaultdict(set);last='';data=b'';sections=[];seen=0
 with gzip.open(O/'relocation_targets.tsv.gz','rt') as src,gzip.open(O/'relro_target_classification.tsv.gz','wt',newline='') as dst:
  inp=csv.DictReader(src,delimiter='\t');fields=['path','target_vaddr','target_file_offset','target_page','reloc_type','target_symbol','container_class','classification','addend_target_section']
  out=csv.DictWriter(dst,fields,delimiter='\t',lineterminator='\n');out.writeheader()
  for r in inp:
   if r['target_section']!='.data.rel.ro':continue
   path=r['path']
   if path!=last:
    last=path;sections=byfile.get(path,[]);file=ROOT/path.lstrip('/')
    data=file.read_bytes() if file.is_file() else b''
   kind=r['container_class'];dest=''
   if kind not in ('vtable','typeinfo'):
    kind='unknown'
    if r['symbol_kind']=='FUNC' and r['symbol_defined']=='1':kind='other_function_pointer_candidate'
    elif r['symbol_kind']=='FUNC':kind='other_function_pointer_candidate'
    elif r['type']=='R_ARM_RELATIVE' and r['target_file_offset']:
     off=int(r['target_file_offset'])
     if off+4<=len(data):
      addr=struct.unpack_from('<I',data,off)[0]
      s=section_for(sections,addr)
      if s:
       dest=s['name']
       if s['name'].startswith(('.text','.plt')):kind='other_function_pointer_candidate'
       elif s['name'].startswith('.rodata') and s['type']!='NOBITS':
        pos=s['fileoff']+addr-s['vaddr']
        end=data.find(b'\0',pos,min(pos+81,len(data)))
        if end>pos and all(32<=b<127 for b in data[pos:end]):kind='string_pointer_candidate'
   counts[kind]+=1;seen+=1
   if r['target_page']:
    page_classes[(path,r['target_page'])].add(kind)
   out.writerow({'path':path,'target_vaddr':r['target_vaddr'],'target_file_offset':r['target_file_offset'],
                 'target_page':r['target_page'],'reloc_type':r['type'],'target_symbol':r['symbol_name'],
                 'container_class':r['container_class'],'classification':kind,'addend_target_section':dest})
   if seen%100000==0:log(f'RELRO classified {seen}')
 weighted=Counter();only=Counter()
 for (path,page),classes in page_classes.items():
  weight=4*int(metrics[path]['mapped_processes'])
  for kind in classes:weighted[kind]+=weight
  if len(classes)==1:only[next(iter(classes))]+=weight
 outsum={'relro_relocation_targets':seen,'target_class_counts':dict(counts),
         'weighted_page_upper_kB_by_class':dict(weighted),
         'weighted_pages_exclusively_one_class_kB':dict(only),
         'classification_rule':'_ZTV/_ZTI defined dynsym OBJECT range; FUNC symbol or REL addend into .text/.plt => function-pointer candidate; REL addend into printable NUL-terminated .rodata => string-pointer candidate; otherwise unknown. Candidates are not proof of source-level table type.'}
 (O/'relro_classification_summary.json').write_text(json.dumps(outsum,ensure_ascii=False,indent=2)+'\n')
 log('RELRO DONE')
if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';log('ERROR '+repr(e));raise
 finally:print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态='+status,flush=True)
