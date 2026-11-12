#!/usr/bin/env python3
"""Run cross_2013 prelink -u only on isolated copies of selected board ELF."""
import csv, hashlib, json, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import preflight as p

HERE=p.HERE
SOURCE=HERE/'pulled_root'
DEST=HERE/'undo_root'
PRELINK=Path('/tmp/prelink-tool-validation-20261112/build-2013/src/prelink')
MARKERS=('.gnu.prelink_undo','.gnu.liblist','.gnu.conflict','GNU_PRELINKED','GNU_LIBLIST','CHECKSUM')

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def readelf(path):
 q=subprocess.run([p.READELF,'-hW','-SW','-dW',str(path)],stdin=subprocess.DEVNULL,capture_output=True,timeout=60)
 return q.returncode,q.stdout.decode(errors='replace'),q.stderr.decode(errors='replace')
def typ(s):
 m=re.search(r'Type:\s+(\S+)',s)
 return m.group(1) if m else ''
def main():
 if not PRELINK.is_file():raise RuntimeError('cross_2013 prelink missing')
 rows=list(csv.DictReader((HERE/'pull_classify.tsv').open(),delimiter='\t'))
 meta={x['path']:x for x in (json.loads(line) for line in (HERE/'metadata.jsonl').open())}
 selected=[r for r in rows if r['selected']=='1' and meta.get(r['path'],{}).get('all_readable')]
 if len(selected)!=434:raise RuntimeError(f'expected 434 metadata-readable targets, got {len(selected)}')
 DEST.mkdir(exist_ok=True)
 with (HERE/'undo_attempt2.tsv').open('w',newline='') as f, (HERE/'undo_errors.log').open('w') as errs:
  w=csv.writer(f,delimiter='\t')
  w.writerow(['path','category','before_sha256','after_sha256','before_bytes','after_bytes','copy_rc','undo_rc','readelf_rc','type_before','type_after','markers_remain','status','stderr_last_line'])
  for i,r in enumerate(selected,1):
   path=r['path'];src=SOURCE/path.lstrip('/');dst=DEST/path.lstrip('/')
   dst.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(src,dst)
   before_sha=sha(dst);before_size=dst.stat().st_size
   before_rc,before_out,before_err=readelf(dst)
   q=subprocess.run([str(PRELINK),f'--root={DEST}','-u',path],stdin=subprocess.DEVNULL,capture_output=True,timeout=60)
   undo_rc=q.returncode
   after_sha=sha(dst) if dst.is_file() else ''
   after_size=dst.stat().st_size if dst.is_file() else 0
   after_rc,after_out,after_err=readelf(dst) if dst.is_file() else (127,'','file missing')
   marker=any(x in after_out for x in MARKERS)
   good=before_rc==0 and undo_rc==0 and after_rc==0 and not marker and typ(before_out)==typ(after_out) and before_sha==r['host_sha256']
   stderr=q.stderr.decode(errors='replace')+before_err+after_err
   if stderr:errs.write(f'===== {path} undo={undo_rc} readelf={after_rc} =====\n{stderr}\n');errs.flush()
   w.writerow([path,r['category'],before_sha,after_sha,before_size,after_size,0,undo_rc,after_rc,typ(before_out),typ(after_out),int(marker),'success' if good else 'failed',stderr.strip().splitlines()[-1] if stderr.strip() else ''])
   f.flush()
   if i%25==0 or i==len(selected):p.log(f'UNDO {i}/{len(selected)}')
 p.log('UNDO done')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
