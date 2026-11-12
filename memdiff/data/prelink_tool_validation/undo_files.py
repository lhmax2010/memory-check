#!/usr/bin/env python3
"""Undo all 425 marked GCC ELF in a private root copy, then validate ELF."""
import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
MEMDIFF=HERE.parents[1]
ROOT=Path('/tmp/prelink-tool-validation-20261112/gcc-undo-root')
PRELINK='/tmp/prelink-tool-validation-20261112/build-2013/src/prelink'
READELF='/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf'
MARKERS=('.gnu.prelink_undo','.gnu.liblist','.gnu.conflict','GNU_PRELINKED','GNU_LIBLIST','CHECKSUM')

def log(msg):print(datetime.now(timezone.utc).isoformat(timespec='seconds'),msg,flush=True)
def main():
 with (MEMDIFF/'data/system_code_page_sections/elf_summary.tsv').open() as f:
  paths=sorted(r['path'] for r in csv.DictReader(f,delimiter='\t') if r['image']=='GCC' and r['prelink_marker_any']=='True')
 if len(paths)!=425:raise RuntimeError(f'expected 425, got {len(paths)}')
 rows=[]; raw=[]
 for i,path in enumerate(paths,1):
  f=ROOT/path.lstrip('/')
  before=f.stat().st_size if f.is_file() else -1
  try:
   run=subprocess.run([PRELINK,f'--root={ROOT}','-u',path],capture_output=True,text=True,timeout=30)
   rc=run.returncode; err=(run.stderr or '').strip()
  except subprocess.TimeoutExpired as exc:
   rc=124;err='timeout after 30 s; '+str(exc.stderr or '')
  after=f.stat().st_size if f.is_file() else -1
  check=subprocess.run([READELF,'-SW','-dW',str(f)],capture_output=True,text=True) if f.is_file() else None
  parse_rc=check.returncode if check else 127
  marker=any(m in check.stdout for m in MARKERS) if check else False
  status='success' if rc==0 and parse_rc==0 and not marker else 'failed'
  rows.append(dict(path=path,before_bytes=before,after_bytes=after,undo_rc=rc,readelf_rc=parse_rc,marker_remains=int(marker),status=status,reason=err.splitlines()[-1] if err else ''))
  if err or parse_rc:
   raw.append(f'===== {path} undo_rc={rc} readelf_rc={parse_rc} =====\n{err}\n{check.stderr if check else "missing file"}\n')
  if i%25==0:log(f'undone {i}/{len(paths)}')
 with (HERE/'undo_results.tsv').open('w',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)
 (HERE/'undo_stderr.log').write_text('\n'.join(raw))
 success=sum(r['status']=='success' for r in rows)
 log(f'undo success {success}/{len(rows)}')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException:
  status='失败';raise
 finally:print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+status,flush=True)
