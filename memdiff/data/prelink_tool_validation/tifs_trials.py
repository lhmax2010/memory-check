#!/usr/bin/env python3
"""Prelink TIFSDaemon in isolated GCC root copies with directory variants."""
import csv
import hashlib
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
TMP=Path('/tmp/prelink-tool-validation-20261112')
BASE=Path(os.environ.get('PRELINK_TRIAL_BASE',str(TMP/'gcc-root')))
PREFIX=os.environ.get('PRELINK_TRIAL_PREFIX','')
if not re.fullmatch(r'[A-Za-z0-9_]*',PREFIX):raise RuntimeError('invalid trial prefix')
TOOL_BUILD=os.environ.get('PRELINK_TRIAL_TOOL_BUILD','build-2013')
if TOOL_BUILD not in ('build-2013','build-cross-latest'):raise RuntimeError('invalid trial tool build')
PRELINK=TMP/TOOL_BUILD/'src/prelink'
RTLD=TMP/TOOL_BUILD/'src/rtld/prelink-rtld'
READELF='/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf'
ORIGINAL_LD='/lib:/usr/lib:/prd/usr/lib:/usr/lib/was-api:/usr/lib/ecore_imf/modules/isf/v-1.13:/usr/lib/gstreamer-1.0:/usr/lib/pulseaudio:/usr/lib/hal'
FKP='/opt/usr/apps/Ddrm/fkp/lib'; HAL='/hal/lib'
TARGET='/usr/bin/TIFSDaemon'
TRIALS=[('baseline',[],[]),('fkp_ld',[FKP],[]),('fkp_ld_conf',[FKP],[FKP]),
        ('fkp_hal_ld',[FKP,HAL],[]),('fkp_hal_ld_conf',[FKP,HAL],[FKP,HAL])]

def log(msg):print(datetime.now(timezone.utc).isoformat(timespec='seconds'),msg,flush=True)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 rows=[]
 for name,ld_add,conf_add in TRIALS:
  root=TMP/f'gcc-tifs-{PREFIX}{name}'
  if root.exists():raise RuntimeError(f'refuse to reuse modified trial root: {root}')
  root.mkdir()
  log(f'{name}: copying isolated root')
  copy=subprocess.run(['cp','-a','--reflink=auto',str(BASE)+ '/.',str(root)],capture_output=True,text=True)
  if copy.returncode:raise RuntimeError(f'{name} root copy failed: {copy.stderr}')
  conf=root/'etc/prelink.conf'
  with conf.open('a') as f:
   for p in conf_add:f.write(f'-l {p}\n')
  ld=ORIGINAL_LD+(':'+':'.join(ld_add) if ld_add else '')
  target=root/TARGET.lstrip('/')
  before=sha(target)
  args=[str(PRELINK),'-fm','--mmap-region-end=0x60000000','--allow-textrel','--verbose',
        f'--root={root}','--config-file=/etc/prelink.conf','--cache-file=/prelink.cache',
        f'--ld-library-path={ld}',f'--rtld={RTLD}',TARGET]
  log(f'{name}: prelink -fm TIFSDaemon')
  try:
   run=subprocess.run(args,capture_output=True,text=True,timeout=120)
   rc=run.returncode;output=run.stdout+run.stderr
  except subprocess.TimeoutExpired as exc:
   rc=124;output='timeout after 120 seconds\n'+str(exc.stdout or '')+'\n'+str(exc.stderr or '')
  (HERE/f'tifs_{PREFIX}{name}.log').write_text('COMMAND: '+' '.join(args)+'\n'+output+f'\nRETURN_CODE={rc}\n')
  check=subprocess.run([READELF,'-SW','-dW',str(target)],capture_output=True,text=True)
  marker=any(s in check.stdout for s in ('.gnu.prelink_undo','GNU_LIBLIST','GNU_PRELINKED'))
  rows.append(dict(trial=name,ld_added=';'.join(ld_add),conf_added=';'.join(conf_add),prelink_rc=rc,
        target_sha_before=before,target_sha_after=sha(target),target_prelink_marker=int(marker),
        readelf_rc=check.returncode,log_file=f'tifs_{PREFIX}{name}.log'))
  log(f'{name}: rc={rc} marker={marker}')
 with (HERE/f'tifs_{PREFIX}trials.tsv').open('w',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException:
  status='失败';raise
 finally:print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+status,flush=True)
