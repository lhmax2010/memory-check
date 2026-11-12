#!/usr/bin/env python3
"""Check assembled roots did not alter any saved GCC ELF byte content."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
MEMDIFF=HERE.parents[1]
SOURCE=MEMDIFF/'data/gcc_baseline/elf/files'
TMP=Path('/tmp/prelink-tool-validation-20261112')
ROOTS={'faithful':TMP/'gcc-root','soname_alias_diagnostic':TMP/'gcc-root-alias'}
def log(msg):print(datetime.now(timezone.utc).isoformat(timespec='seconds'),msg,flush=True)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 rows=[];paths=sorted(p for p in SOURCE.rglob('*') if p.is_file())
 for i,source in enumerate(paths,1):
  rel=source.relative_to(SOURCE);original=sha(source)
  for name,root in ROOTS.items():
   p=root/rel
   copied=sha(p) if p.is_file() else ''
   rows.append(dict(root=name,path='/'+str(rel),source_sha256=original,root_sha256=copied,same=int(bool(copied) and original==copied)))
  if i%100==0:log(f'hash checked {i}/{len(paths)}')
 with (HERE/'root_integrity.tsv').open('w',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)
 summary={name:{'files':sum(r['root']==name for r in rows),'identical':sum(r['root']==name and r['same']==1 for r in rows)} for name in ROOTS}
 (HERE/'root_integrity_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 log(str(summary))
if __name__=='__main__':
 state='成功'
 try:main()
 except BaseException:
  state='失败';raise
 finally:print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+state,flush=True)
