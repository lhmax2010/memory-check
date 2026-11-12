#!/usr/bin/env python3
"""Create a separate diagnostic root with SONAME-backed symlinks only."""
import csv
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
TMP=Path('/tmp/prelink-tool-validation-20261112')
SOURCE=TMP/'gcc-root'; DEST=TMP/'gcc-root-alias'
def log(msg):print(datetime.now(timezone.utc).isoformat(timespec='seconds'),msg,flush=True)

def main():
 if DEST.exists():raise RuntimeError(f'refuse to overwrite {DEST}')
 DEST.mkdir()
 log('copy pristine GCC root for inferred SONAME link diagnostic')
 r=subprocess.run(['cp','-a','--reflink=auto',str(SOURCE)+'/.',str(DEST)],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr)
 with (HERE/'elf_dynamic.tsv').open() as f:
  dynamic=list(csv.DictReader(f,delimiter='\t'))
 by_alias=defaultdict(set)
 for row in dynamic:
  name=row['soname'];path=row['path']
  if name and name!=Path(path).name:
   alias=str(Path(path).parent/name)
   by_alias[alias].add(path)
 rows=[]
 for alias,candidates in sorted(by_alias.items()):
  if len(candidates)!=1:
   rows.append(dict(alias=alias,target=';'.join(sorted(candidates)),status='ambiguous; skipped'))
   continue
  target=next(iter(candidates)); a=DEST/alias.lstrip('/')
  if a.exists() or a.is_symlink():
   rows.append(dict(alias=alias,target=target,status='already existed; skipped'))
   continue
  a.parent.mkdir(parents=True,exist_ok=True)
  a.symlink_to(Path(target).name)
  rows.append(dict(alias=alias,target=target,status='inferred from DT_SONAME; symlink created'))
 with (HERE/'inferred_aliases.tsv').open('w',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)
 log(f'created {sum(r["status"].startswith("inferred") for r in rows)} symlinks; no ELF bytes synthesized')

if __name__=='__main__':
 state='成功'
 try:main()
 except BaseException:
  state='失败';raise
 finally:print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+state,flush=True)
