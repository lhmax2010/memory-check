#!/usr/bin/env python3
"""Temporary native readelf screens all board ELF; host cross readelf is final authority."""
import json, os, re, subprocess, sys
from pathlib import Path
import preflight as p

HERE=p.HERE
STAGE='/root/prelink_ab_tools'
NATIVE='/home/linhao/lss/memory_check/round3e_gbs_work/gcc_root/local/BUILD-ROOTS/scratch.armv7l.0/usr/bin/readelf'
ROOT='/home/linhao/lss/memory_check/round3e_gbs_work/gcc_root/local/BUILD-ROOTS/scratch.armv7l.0'

def main():
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 src=HERE/'all_elf_paths.txt'
 if not src.is_file() or not src.stat().st_size:raise RuntimeError('all_elf_paths empty')
 root=False; stage=False
 try:
  rc,_,_=p.run('scan_root_on',[p.SDB,'-s',p.IP,'root','on'])
  if rc:raise RuntimeError('root on failed')
  root=True
  rc,uid,_=p.board('scan_uid','id -u')
  if rc or uid.strip()!='0':raise RuntimeError('root UID missing')
  rc,_,_=p.board('scan_stage_absent',f'test ! -e {STAGE}')
  if rc:raise RuntimeError('stage path already exists')
  rc,_,_=p.board('scan_stage_create',f'mkdir -m 700 {STAGE}')
  if rc:raise RuntimeError('stage mkdir failed')
  stage=True
  items=[('readelf',NATIVE),('elf_paths.txt',str(src)),('libctf-nobfd.so.0',ROOT+'/usr/lib/libctf-nobfd.so.0.0.0'),('libsframe.so.1',ROOT+'/usr/lib/libsframe.so.1.0.0')]
  for name,source in items:
   rc,_,_=p.run('scan_push_'+name,[p.SDB,'-s',p.IP,'push',source,f'{STAGE}/{name}'],120)
   if rc:raise RuntimeError('push failed '+name)
  rc,out,_=p.board('scan_readelf_version',f'LD_LIBRARY_PATH={STAGE} {STAGE}/readelf --version')
  if rc:raise RuntimeError('native readelf cannot execute')
  count=sum(1 for x in src.read_text().splitlines() if x)
  script=f'''n=0; failures=0; while IFS= read -r f; do
    [ -n "$f" ] || continue
    LD_LIBRARY_PATH={STAGE} {STAGE}/readelf -dW "$f" > {STAGE}/one.dynamic 2> {STAGE}/one.err
    r=$?
    if [ "$r" -ne 0 ]; then printf 'READ_ERROR\\t%s\\t%s\\n' "$f" "$r"; failures=$((failures+1)); fi
    if grep -qF '(GNU_PRELINKED)' {STAGE}/one.dynamic; then printf 'GNU_PRELINKED\\t%s\\n' "$f"; fi
    n=$((n+1)); if [ $((n%100)) -eq 0 ]; then printf 'PROGRESS\\t%s\\n' "$n"; fi
  done < {STAGE}/elf_paths.txt
  printf 'SUMMARY\\t%s\\t%s\\n' "$n" "$failures"
  test "$n" -eq {count} && test "$failures" -eq 0'''
  wrapped=script+"; __ab_rc=$?; printf '\\n__AB_RC__%d\\n' \"$__ab_rc\""
  argv=[p.SDB,'-s',p.IP,'shell',wrapped]
  p.log('RUN native_prelinked_scan')
  output=[]
  with (p.RAW/'native_prelinked_scan.stdout').open('wb') as stdout_file:
   proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   for line in proc.stdout:
    stdout_file.write(line); stdout_file.flush()
    decoded=line.decode(errors='replace').strip()
    output.append(decoded)
    if decoded.startswith('PROGRESS\t'):p.log(decoded)
   stderr=proc.stderr.read(); transport_rc=proc.wait(timeout=1800)
  (p.RAW/'native_prelinked_scan.stderr').write_bytes(stderr)
  out='\n'.join(output)
  match=re.search(r'__AB_RC__(\d+)\s*$',out)
  rc=transport_rc or (int(match.group(1)) if match else 255)
  (p.RAW/'native_prelinked_scan.json').write_text(json.dumps({'time':p.now(),'argv':argv,'transport_rc':transport_rc,'remote_rc':rc,'stdout_bytes':(p.RAW/'native_prelinked_scan.stdout').stat().st_size,'stderr_bytes':len(stderr)},ensure_ascii=False,indent=2)+'\n')
  paths=sorted(set(x.split('\t',1)[1] for x in out.splitlines() if x.startswith('GNU_PRELINKED\t')))
  (HERE/'native_gnu_prelinked_paths.txt').write_text('\n'.join(paths)+'\n')
  (HERE/'native_scan_summary.json').write_text(json.dumps({'expected_elf_paths':count,'native_gnu_prelinked':len(paths),'remote_rc':rc,'summary_lines':[x for x in out.splitlines() if x.startswith('SUMMARY\t')],'native_readelf_version':(p.RAW/'scan_readelf_version.stdout').read_text(errors='replace').strip()},indent=2)+'\n')
  p.log(f'native scan complete: {len(paths)} GNU_PRELINKED paths; rc={rc}')
  if rc:raise RuntimeError('native scan failed')
 finally:
  if root:
   if stage:p.board('scan_stage_cleanup',f'rm -f {STAGE}/readelf {STAGE}/elf_paths.txt {STAGE}/libctf-nobfd.so.0 {STAGE}/libsframe.so.1 {STAGE}/one.dynamic {STAGE}/one.err; rmdir {STAGE}; test ! -e {STAGE}')
   p.run('scan_root_off',[p.SDB,'-s',p.IP,'root','off'])
   rc,uid,_=p.board('scan_sdk_uid','id -u')
   if rc or uid.strip()=='0':raise RuntimeError('sdb root off failed')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
