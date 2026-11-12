#!/usr/bin/env python3
"""Capture 20 recreated ELF files with a diagnostic-only prelink build."""
import csv
import gzip
import hashlib
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
TMP=Path('/tmp/prelink-tool-validation-20261112')
ROOT=TMP/'gcc-root-alias'
PRELINK=TMP/'build-diagnostic/src/prelink'
RTLD=TMP/'build-diagnostic/src/rtld/prelink-rtld'
READELF='/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf'
LD='/lib:/usr/lib:/prd/usr/lib:/usr/lib/was-api:/usr/lib/ecore_imf/modules/isf/v-1.13:/usr/lib/gstreamer-1.0:/usr/lib/pulseaudio:/usr/lib/hal'
SEC=re.compile(r'^\s*\[\s*(\d+)\]\s+(\S+)\s+(\S+)\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s')
def log(msg):print(datetime.now(timezone.utc).isoformat(timespec='seconds'),msg,flush=True)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def sections(path):
 r=subprocess.run([READELF,'-SW',str(path)],capture_output=True,text=True)
 out={}
 for line in r.stdout.splitlines():
  m=SEC.match(line)
  if m:
   key=(m[2],m[1]);out[key]=(m[3],int(m[4],16),int(m[5],16))
 return r,out

def main():
 with (HERE/'alias_verify_results.tsv').open() as f:
  paths=[r['path'] for r in csv.DictReader(f,delimiter='\t') if r['version']=='cross_latest' and r['status']=='byte_different_internal_verify'][:20]
 if len(paths)!=20:raise RuntimeError(f'expected 20 mismatches, got {len(paths)}')
 captures=TMP/'mismatch-captures';captures.mkdir(exist_ok=True)
 rows=[]; raw=[]
 for i,path in enumerate(paths,1):
  original=ROOT/path.lstrip('/')
  recreated=captures/f'{i:02d}.elf'
  env=os.environ.copy();env['PRELINK_CAPTURE_FILE']=str(recreated)
  cmd=[str(PRELINK),f'--root={ROOT}','--verify','--mmap-region-end=0x60000000','--allow-textrel',
       f'--ld-library-path={LD}',f'--rtld={RTLD}','--config-file=/etc/prelink.conf','--cache-file=/prelink.cache',path]
  run=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,env=env,timeout=60)
  if not recreated.is_file():
   rows.append(dict(path=path,verify_rc=run.returncode,capture_status='missing',original_bytes=original.stat().st_size,recreated_bytes='',
      original_sha256=sha(original),recreated_sha256='',changed_sections='',section_size_deltas='',headers_padding_delta_bytes=''))
   continue
  ra,sa=sections(original);rb,sb=sections(recreated)
  if ra.returncode or rb.returncode:raise RuntimeError(f'readelf failed for {path}: {ra.stderr} {rb.stderr}')
  original_bytes=original.read_bytes(); recreated_bytes=recreated.read_bytes()
  changed=[]; size_deltas=[]
  for key in sorted(set(sa)|set(sb)):
   a=sa.get(key);b=sb.get(key)
   name=key[0] or '[NULL]'
   size_a=a[2] if a else 0;size_b=b[2] if b else 0
   if size_a!=size_b:size_deltas.append(f'{name}:{size_b-size_a:+d}')
   payload_a=original_bytes[a[1]:a[1]+a[2]] if a and a[0]!='NOBITS' else b''
   payload_b=recreated_bytes[b[1]:b[1]+b[2]] if b and b[0]!='NOBITS' else b''
   if payload_a!=payload_b or bool(a)!=bool(b):changed.append(name)
  pa=original.stat().st_size-sum(a[2] for a in sa.values() if a[0]!='NOBITS')
  pb=recreated.stat().st_size-sum(b[2] for b in sb.values() if b[0]!='NOBITS')
  rows.append(dict(path=path,verify_rc=run.returncode,capture_status='captured',original_bytes=original.stat().st_size,
      recreated_bytes=recreated.stat().st_size,original_sha256=sha(original),recreated_sha256=sha(recreated),
      changed_sections=';'.join(sorted(set(changed))),section_size_deltas=';'.join(size_deltas),headers_padding_delta_bytes=pb-pa))
  raw.append(f'===== {path} ORIGINAL =====\n{ra.stdout}\n===== RECREATED =====\n{rb.stdout}\nSTDERR: {run.stderr}\n')
  log(f'captured {i}/{len(paths)} {path}')
 with (HERE/'mismatch_sections_top20.tsv').open('w',newline='') as f:
  w=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)
 with gzip.open(HERE/'mismatch_readelf_top20.txt.gz','wt') as f:f.write('\n'.join(raw))
 (HERE/'diagnostic_capture_tool.sha256').write_text(f'{sha(PRELINK)}  {PRELINK}\n')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException:
  status='失败';raise
 finally:print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+status,flush=True)
