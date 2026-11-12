#!/usr/bin/env python3
"""Run upstream prelink --verify against saved GCC prelinked ELF copies.

--verify itself undoes and redoes prelink, byte-compares the recreated
prelinked file with the input, then writes the *undone* ELF to stdout.
The output bytes therefore must not be compared directly with input bytes.
"""
import csv
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
MEMDIFF=HERE.parents[1]
TMP=Path('/tmp/prelink-tool-validation-20261112')
ROOT=Path(os.environ.get('PRELINK_ROOT',str(TMP/'gcc-root')))
PREFIX=os.environ.get('PRELINK_RESULT_PREFIX','')
if not re.fullmatch(r'[A-Za-z0-9_]*',PREFIX):raise RuntimeError('invalid output prefix')
DATA=MEMDIFF/'data/system_code_page_sections/elf_summary.tsv'
LD='/lib:/usr/lib:/prd/usr/lib:/usr/lib/was-api:/usr/lib/ecore_imf/modules/isf/v-1.13:/usr/lib/gstreamer-1.0:/usr/lib/pulseaudio:/usr/lib/hal'
VERSIONS={
 'cross_2013':(TMP/'build-2013/src/prelink',TMP/'build-2013/src/rtld/prelink-rtld','f82b486136b89619aea2c1462d3c2da7925eec15','origin/cross_prelink 2013-04-23'),
 'cross_latest':(TMP/'build-cross-latest/src/prelink',TMP/'build-cross-latest/src/rtld/prelink-rtld','f9975537dbfd9ade0fc813bd5cf5fcbe41753a37','origin/cross_prelink 2019-06-24'),
 'master_2024':(TMP/'build-master-2024/src/prelink',None,'ff2561c02ade96c5d4d56ddd4e27ff064840a176','origin/master 2024-07-02'),
}

def log(msg):print(datetime.now(timezone.utc).isoformat(timespec='seconds'),msg,flush=True)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def out(name):return HERE/(PREFIX+name)
def tsv(name,rows,fields):
 with out(name).open('w',newline='') as f:
  w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
 with DATA.open() as f:
  marked=sorted(r['path'] for r in csv.DictReader(f,delimiter='\t') if r['image']=='GCC' and r['prelink_marker_any']=='True')
 if len(marked)!=425:raise RuntimeError(f'expected 425 marked ELF, got {len(marked)}')
 if not (ROOT/'etc/prelink.conf').is_file():raise RuntimeError('root prelink.conf missing')
 binary_rows=[]; results=[]; raw=[]
 for version,(prelink,rtld,commit,branch) in VERSIONS.items():
  if not prelink.is_file() or (rtld is not None and not rtld.is_file()):raise RuntimeError(f'{version} binaries missing')
  help_run=subprocess.run([str(prelink),'--help'],capture_output=True,text=True)
  help_text=help_run.stdout+help_run.stderr
  binary_rows.append(dict(version=version,branch=branch,commit=commit,prelink_path=str(prelink),prelink_sha256=sha(prelink),
     rtld_path=str(rtld) if rtld else '',rtld_sha256=sha(rtld) if rtld else '',
     help_has_root=int('--root' in help_text),help_has_verify=int('--verify' in help_text),
     source_has_ignore_soname=0))
  out(f'help_{version}.txt').write_text(help_text)
  log(f'{version}: validate {len(marked)} prelinked copies')
  for i,path in enumerate(marked,1):
   if not (ROOT/path.lstrip('/')).is_file():
    results.append(dict(version=version,path=path,rc=127,status='error',reason='ELF copy absent from assembled root'))
    continue
   args=[str(prelink),f'--root={ROOT}','--verify','--mmap-region-end=0x60000000','--allow-textrel',
      f'--ld-library-path={LD}','--config-file=/etc/prelink.conf','--cache-file=/prelink.cache']
   if rtld:args.append(f'--rtld={rtld}')
   args.append(path)
   try:
    r=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=30)
    err=r.stderr.strip(); rc=r.returncode
   except subprocess.TimeoutExpired as exc:
    err='timeout after 30 s; '+(exc.stderr.decode(errors='replace') if isinstance(exc.stderr,bytes) else str(exc.stderr or ''))
    rc=124
   reason=err.splitlines()[-1] if err else ''
   if rc==0:status='byte_identical_internal_verify'
   elif 'prelinked file was modified' in err or 'prelinked file size differs' in err:status='byte_different_internal_verify'
   else:status='error'
   results.append(dict(version=version,path=path,rc=rc,status=status,reason=reason))
   if err:raw.append(f'===== {version} {path} rc={rc} status={status} =====\n{err}\n')
   if i%25==0:log(f'{version}: {i}/{len(marked)}')
  log(f'{version}: '+str(Counter(r['status'] for r in results if r['version']==version)))
 tsv('tool_versions.tsv',binary_rows,list(binary_rows[0]))
 tsv('verify_results.tsv',results,list(results[0]))
 out('verify_stderr.log').write_text('\n'.join(raw))
 counts=[]
 for version in VERSIONS:
  c=Counter(r['status'] for r in results if r['version']==version)
  counts.append(dict(version=version,total=len(marked),byte_identical=c['byte_identical_internal_verify'],
      byte_different=c['byte_different_internal_verify'],error=c['error']))
 tsv('verify_summary.tsv',counts,list(counts[0]))
 out('verify_command.json').write_text(json.dumps(dict(root=str(ROOT),ld_library_path=LD,common_options=['--verify','--mmap-region-end=0x60000000','--allow-textrel','--config-file=/etc/prelink.conf','--cache-file=/prelink.cache'],
    unsupported_vd_option='--ignore-soname; omitted because all upstream versions reject it',timeout_seconds=30),indent=2)+'\n')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException:
  status='失败';raise
 finally:print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+status,flush=True)
