#!/usr/bin/env python3
"""Read existing ELF copies for a bounded, reproducible hotspot selection."""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime

ROOT=Path(__file__).resolve().parents[2]
READELF=Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf')
SOURCES={
 'GCC':ROOT/'memdiff/data/gcc_baseline/elf/files',
 'LLVM3':ROOT/'memdiff/data/llvm_round3/elf/files',
 'noPIE':ROOT/'memdiff/data/noPIE_prelink_validation/boots/boot1/collection/elf',
}
SECTION=re.compile(r'^\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+')

def rows(path):
 with path.open(newline='') as f:yield from csv.DictReader(f,delimiter='\t')
def write(path,data):
 if not data:return
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,list(data[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(data)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def run(out):
 out.mkdir(parents=True,exist_ok=True)
 scores={}; reasons={}
 for r in rows(out/'C_file_comparisons.tsv'):
  if float(r['delta_total_kB'])<=0:continue
  p=r['path']
  if not p.startswith('/'):continue
  score=float(r['delta_total_kB'])
  if score>scores.get(p,-1):scores[p]=score;reasons[p]='file '+r['comparison']
 for r in rows(out/'C_process_comparisons.tsv'):
  if float(r['delta_total_kB'])<=0:continue
  p=r['identity_key'].split(' | ',1)[-1]
  score=float(r['delta_total_kB'])
  if score>scores.get(p,-1):scores[p]=score;reasons[p]='main executable '+r['comparison']
 # Rank by the largest observed positive contribution; process and file scores
 # are alternative views and must never be added.
 selected=[]
 for p in sorted(scores,key=lambda p:(-scores[p],p)):
  if any((root/p.lstrip('/')).is_file() for root in SOURCES.values()):
   selected.append(p)
  if len(selected)==10:break
 argot_paths=['/usr/apps/com.samsung.tizen.argot/bin/argot',
              '/opt/usr/share/argot/.local/bin/tsr',
              '/opt/usr/share/argot/.local/bin/tsr-bwrap']
 selection=[dict(rank=i+1,path=p,selection_score_kB=scores[p],reason=reasons[p],scope='A_top10') for i,p in enumerate(selected)]
 selection += [dict(rank=i+11,path=p,selection_score_kB='NA',reason='B historical comparability',scope='B_argot') for i,p in enumerate(argot_paths)]
 write(out/'static_selection.tsv',selection)
 prelinked=set(json.loads((ROOT/'memdiff/data/llvm_round3/analysis/classification.json').read_text())['GCC_prelinked_LLVM3_unmarked'])
 records=[]
 for i,p in enumerate(selected+argot_paths,1):
  for image,root in SOURCES.items():
   local=root/p.lstrip('/')
   rec=dict(rank=i,path=p,image=image,source=str(local.relative_to(ROOT)),available=int(local.is_file()),
    in_original_410=int(p in prelinked))
   if not local.is_file():records.append(rec);continue
   proc=subprocess.run([str(READELF),'-hW','-SW','-lW','-dW','-nW',str(local)],capture_output=True,text=True,errors='replace')
   raw=proc.stdout+'\nSTDERR:\n'+proc.stderr
   rawname=f'elf_{i:02d}_{image}.readelf.txt.gz'
   with (out/rawname).open('wb') as binary:
    with gzip.GzipFile(fileobj=binary,mode='wb',filename='',mtime=0) as compressed:
     compressed.write(raw.encode())
   rec.update(sha256=sha(local),size_bytes=local.stat().st_size,readelf_rc=proc.returncode,readelf_output=rawname)
   if proc.returncode:records.append(rec);continue
   m=re.search(r'^\s*Type:\s+(\S+)',raw,re.M);rec['ELF_type']=m.group(1) if m else 'unknown'
   rec['PIE_flag']=int(any('FLAGS_1' in line and 'PIE' in line for line in raw.splitlines()))
   m=re.search(r'Build ID:\s+([0-9a-fA-F]+)',raw);rec['build_id']=m.group(1) if m else 'not_found'
   sections={m.group(1):int(m.group(2),16) for line in raw.splitlines() if (m:=SECTION.match(line))}
   for sec in ('.text','.rodata','.dynsym','.dynstr','.rel.dyn','.rela.dyn','.rel.plt','.rela.plt','.gnu.conflict'):
    rec[sec+'_bytes']=sections.get(sec,0)
   rec['relocation_sections_bytes']=sum(v for k,v in sections.items() if k.startswith(('.rel.','.rela.')))
   rec['prelink_undo']=int('.gnu.prelink_undo' in sections)
   rec['gnu_liblist']=int('.gnu.liblist' in sections)
   rec['GNU_PRELINKED_dynamic']=int('GNU_PRELINKED' in raw)
   loads=[]
   for line in raw.splitlines():
    if line.lstrip().startswith('LOAD '):loads.append(' '.join(line.split()))
   rec['PT_LOAD']='; '.join(loads)
   if '.comment' in sections:
    comment=subprocess.run([str(READELF),'-p','.comment',str(local)],capture_output=True,text=True,errors='replace')
    rec['comment_rc']=comment.returncode
    rec['comment']=' | '.join(line.strip() for line in comment.stdout.splitlines() if '[' in line and ']' in line)[:700]
   else:rec['comment']='section absent';rec['comment_rc']=0
   records.append(rec)
   print(datetime.now().astimezone().isoformat(),i,image,p,flush=True)
 # Uniform columns even when one side is unavailable.
 fields=list(dict.fromkeys(k for r in records for k in r))
 with (out/'static_elf_evidence.tsv').open('w',newline='') as f:
  w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader()
  for record in records:w.writerow({k:record.get(k,'NA') for k in fields})
 (out/'static_tool.json').write_text(json.dumps({'readelf':str(READELF),'readelf_sha256':sha(READELF),
  'selected_A_count':len(selected),'selected_B_count':len(argot_paths),
  'selection':'largest positive process OR file delta; never summed'},indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();status='成功'
 try:run(a.out)
 except Exception:status='失败';raise
 finally:print('已结束',datetime.now().astimezone().isoformat(),'状态='+status,flush=True)
