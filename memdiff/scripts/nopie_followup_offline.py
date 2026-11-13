#!/usr/bin/env python3
"""Read-only follow-up of saved noPIE, GCC and LLVM ELF/process snapshots."""
import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'memdiff/data'
READELF = Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf')
SOURCES = {
    'noPIE': DATA/'noPIE_prelink_validation/boots/boot2/collection/elf',
    'GCC': DATA/'gcc_baseline/elf/files',
    'LLVM3': DATA/'llvm_round3/elf/files',
}

def write_tsv(path, rows, fields):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fields, delimiter='\t', extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        w.writerows([{k: ('NA' if v is None or v == '' else v) for k, v in row.items()} for row in rows])

def load_processes(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))

def pss(row):
    return float(row['Pss_total_kB']) + float(row['SwapPss_kB'])

def process_comparison(out):
    cls=json.loads((DATA/'llvm_round3/analysis/classification.json').read_text())
    programs=set(cls['GCC_nonPIE'])
    boots={}
    for image,prefix in (('gcc_baseline','GCC'),('llvm_round3','LLVM3')):
      for n in (1,2):
        matches=list((DATA/image/f'boot{n}').glob('memcheck/*/02_steady/smaps_raw.txt.gz'))
        if len(matches)!=1:raise RuntimeError(f'archive count {prefix}{n}: {matches}')
        records=[]; cur=None
        with gzip.open(matches[0],'rt',errors='replace') as stream:
          for line in stream:
            if line.startswith('### '):
              if cur:records.append(cur)
              b=line.rstrip().split(' ',3)
              if len(b)<3:
                cur=None
                continue
              cur={'boot':f'{prefix}{n}','pid':b[1],'name':b[2], 'exe':b[3] if len(b)>3 else '', 'Pss_SwapPss_kB':0}
            elif cur and (line.startswith('Pss:') or line.startswith('SwapPss:')):
              m=re.match(r'^(?:Pss|SwapPss):\s+(\d+)',line)
              if m:cur['Pss_SwapPss_kB']+=int(m[1])
          if cur:records.append(cur)
        boots[f'{prefix}{n}']=records
        with (out/'progress.log').open('a') as f:f.write(f'{datetime.now().astimezone().isoformat()} parsed {prefix}{n} {len(records)} processes\n')
    for n in (1,2):
      rows=[]
      for r in load_processes(DATA/f'noPIE_prelink_validation/boots/boot{n}/budget/process_budget.tsv'):
        rows.append({'boot':f'noPIE{n}','name':r['name'],'exe':r['exe'],'pid':r['pid'],'Pss_SwapPss_kB':pss(r)})
      boots[f'noPIE{n}']=rows
    allrows=[r for rows in boots.values() for r in rows]
    write_tsv(out/'process_smaps_same_source.tsv',allrows,['boot','name','exe','pid','Pss_SwapPss_kB'])
    counts={b:{} for b in boots}
    for b,rows in boots.items():
      for r in rows:
        key=(r['name'],r['exe']);counts[b][key]=counts[b].get(key,0)+1
    strict={key for key in counts['GCC1'] if all(counts[b].get(key)==1 for b in boots)}
    strict_rows=[]
    for b,rows in boots.items():
      for r in rows:
        if (r['name'],r['exe']) in strict:
          strict_rows.append(r)
    write_tsv(out/'strict_common_processes.tsv',strict_rows,['boot','name','exe','pid','Pss_SwapPss_kB'])
    summary=[]
    for b,rows in boots.items():
      summary.append({'boot':b,'process_count':len(rows),'strict_common_identities':len(strict),
        'all_Pss_SwapPss_kB':round(sum(float(r['Pss_SwapPss_kB']) for r in rows),3),
        'strict_common_Pss_SwapPss_kB':round(sum(float(r['Pss_SwapPss_kB']) for r in rows if (r['name'],r['exe']) in strict),3),
        'fixed15_Pss_SwapPss_kB':round(sum(float(r['Pss_SwapPss_kB']) for r in rows if r['exe'] in programs),3),
        'fixed15_instances':sum(r['exe'] in programs for r in rows),
        'fixed15_paths_present':len({r['exe'] for r in rows if r['exe'] in programs})})
    write_tsv(out/'process_group_summary.tsv',summary,list(summary[0]))
    presence=[]
    for path in sorted(programs):
      row={'exe':path}
      for b,rows in boots.items():row[b]=sum(r['exe']==path for r in rows)
      presence.append(row)
    write_tsv(out/'fixed15_presence.tsv',presence,list(presence[0]))

def elf_scan(out):
    fields=['image','path','sha256','elf_type','DT_TEXTREL','DT_FLAGS_TEXTREL','status','stderr']
    rows=[]
    for image, root in SOURCES.items():
        files=sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink())
        for i,p in enumerate(files,1):
            try:
                with p.open('rb') as f: magic=f.read(4)
            except OSError as e:
                rows.append(dict(image=image,path='/'+str(p.relative_to(root)),status='read_error',stderr=str(e)));continue
            if magic!=b'\x7fELF':continue
            rel='/'+str(p.relative_to(root))
            h=hashlib.sha256()
            with p.open('rb') as f:
                for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
            try:
                q=subprocess.run([str(READELF),'-hW','-dW',str(p)],capture_output=True,text=True,timeout=15)
                raw=q.stdout
                etype=re.search(r'^\s*Type:\s+(\S+)',raw,re.M)
                rows.append(dict(image=image,path=rel,sha256=h.hexdigest(),elf_type=etype.group(1) if etype else '',
                  DT_TEXTREL=int(bool(re.search(r'\(TEXTREL\)',raw))),
                  DT_FLAGS_TEXTREL=int(bool(re.search(r'\(FLAGS\).*TEXTREL',raw))),
                  status='ok' if q.returncode==0 else f'readelf_rc_{q.returncode}',stderr=q.stderr.strip().replace('\n',' | ')))
            except subprocess.TimeoutExpired:
                rows.append(dict(image=image,path=rel,sha256=h.hexdigest(),status='readelf_timeout'))
            if i%100==0:
                with (out/'progress.log').open('a') as f:f.write(f'{datetime.now().astimezone().isoformat()} {image} {i}/{len(files)}\n')
    write_tsv(out/'textrel_scan.tsv',rows,fields)
    by={}
    for r in rows:by.setdefault(r['image'],{})[r['path']]=r
    current=by.get('noPIE',{})
    diff=[]
    for p,r in current.items():
        if r['status']!='ok':continue
        if not (r['DT_TEXTREL'] or r['DT_FLAGS_TEXTREL']):continue
        for old in ('GCC','LLVM3'):
            x=by.get(old,{}).get(p)
            state='unavailable' if not x or x['status']!='ok' else ('existing' if x['DT_TEXTREL'] or x['DT_FLAGS_TEXTREL'] else 'new')
            diff.append({'path':p,'versus':old,'classification':state,'sha256':r['sha256']})
    write_tsv(out/'textrel_current_diff.tsv',diff,['path','versus','classification','sha256'])
    summary={k:{'scanned':sum(r['image']==k for r in rows),'parse_ok':sum(r['image']==k and r['status']=='ok' for r in rows),
      'textrel':sum(r['image']==k and (r['DT_TEXTREL'] or r['DT_FLAGS_TEXTREL']) for r in rows if 'DT_TEXTREL' in r)} for k in SOURCES}
    (out/'textrel_summary.json').write_text(json.dumps(summary,indent=2))
    return summary

def main():
    a=argparse.ArgumentParser();a.add_argument('--out',type=Path,required=True);a.add_argument('--process-only',action='store_true');args=a.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    try:
        process_comparison(args.out)
        if not args.process_only:
            summary=elf_scan(args.out)
            print(json.dumps(summary,ensure_ascii=False))
        print('已结束',datetime.now().astimezone().isoformat(),'状态=成功')
    except Exception as e:
        print('已结束',datetime.now().astimezone().isoformat(),'状态=失败',repr(e),file=sys.stderr)
        raise
if __name__=='__main__':main()
