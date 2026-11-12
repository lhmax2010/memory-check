#!/usr/bin/env python3
"""Read-only GCC board identity and tvs-daemon prelink gate."""
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
BOARD=HERE/'board_preflight'
BOARD.mkdir(parents=True,exist_ok=True)
IP=os.environ.get('PRELINK_BOARD_IP','192.168.108.26')
SDB='/home/linhao/tizen-studio/tools/sdb'
READELF='/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf'
GCC_OLD=HERE.parents[1]/'data/gcc_baseline/elf/files/usr/bin/tvs-daemon'
ALLOW_UNDO=os.environ.get('PRELINK_ALLOW_UNDO_MARKER')=='1'

def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def log(msg):print(stamp(),msg,flush=True)
def run(name,args,timeout=30):
 result=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
 (BOARD/(name+'.stdout')).write_bytes(result.stdout)
 (BOARD/(name+'.stderr')).write_bytes(result.stderr)
 (BOARD/(name+'.json')).write_text(json.dumps({'time':stamp(),'argv':args,'rc':result.returncode},ensure_ascii=False,indent=2)+'\n')
 return result.returncode,result.stdout.decode(errors='replace')
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 state={'time':stamp(),'ip':IP,'allow_undo_marker':ALLOW_UNDO,'status':'started'}
 try:
  log('connect '+IP)
  rc,out=run('connect',[SDB,'connect',IP],15)
  if rc!=0:raise RuntimeError('sdb_connect_failed')
  remote='''printf '__ARCH__\\n'; uname -m; printf '__MODEL__\\n'; cat /proc/device-tree/model; printf '\\n__CMDLINE__\\n'; cat /proc/cmdline; printf '__VERSION__\\n'; cat /proc/version; printf '__BUILD__\\n'; sed -n 's/^BUILD_ID=//p' /etc/os-release; printf '__BOOTID__\\n'; cat /proc/sys/kernel/random/boot_id; printf '__UID__\\n'; id -u'''
  rc,out=run('identity',[SDB,'-s',IP,'shell',remote],30)
  names=['ARCH','MODEL','CMDLINE','VERSION','BUILD','BOOTID','UID']
  fields={}
  for i,name in enumerate(names):
   m=re.search(r'__'+name+r'__\s*\n(.*?)(?=__[A-Z]+__|\Z)',out,re.S)
   fields[name]=m.group(1).strip().replace('\x00','') if m else ''
  checks={'sdb_rc':rc==0,'armv7l':fields['ARCH']=='armv7l','NT72671D':'NT72671D' in fields['MODEL'],
          'KSU2E':bool(re.search(r'dtsversion=\S*KSU2E',fields['CMDLINE'])),'gcc_kernel':'gcc' in fields['VERSION'].lower(),
          'BUILD_ID_present':bool(fields['BUILD']),'boot_id_present':bool(fields['BOOTID'])}
  state.update(identity=fields,identity_checks=checks)
  (BOARD/'identity_parsed.json').write_text(json.dumps({'fields':fields,'checks':checks},ensure_ascii=False,indent=2)+'\n')
  if not all(checks.values()):raise RuntimeError('identity_gate_failed')
  log('identity passed, checking tvs-daemon ELF without board modification')
  rc,out=run('board_sha',[SDB,'-s',IP,'shell','sha256sum /usr/bin/tvs-daemon'],30)
  if rc!=0:raise RuntimeError('board_tvs_sha_failed')
  board_hash=out.strip().split()[0] if out.strip() else ''
  if not re.fullmatch(r'[0-9a-f]{64}',board_hash):raise RuntimeError('board_tvs_sha_invalid')
  local=HERE/'tvs-daemon.board'
  rc,_=run('pull_tvs',[SDB,'-s',IP,'pull','/usr/bin/tvs-daemon',str(local)],120)
  if rc!=0 or not local.is_file():raise RuntimeError('tvs_pull_failed')
  host_hash=sha(local);old_hash=sha(GCC_OLD)
  state.update(tvs_board_sha256=board_hash,tvs_host_sha256=host_hash,tvs_gcc_20261102_sha256=old_hash)
  if board_hash!=host_hash:raise RuntimeError('board_host_sha_mismatch')
  for name,args in [('sections',[READELF,'-SW',str(local)]),('dynamic',[READELF,'-dW',str(local)]),('header',[READELF,'-hW',str(local)])]:
   rc,text=run('tvs_'+name,args,30)
   if rc!=0:raise RuntimeError('readelf_'+name+'_failed')
  sec=(BOARD/'tvs_sections.stdout').read_text();dyn=(BOARD/'tvs_dynamic.stdout').read_text()
  markers={'GNU_LIBLIST':'(GNU_LIBLIST)' in dyn,'GNU_PRELINKED':'(GNU_PRELINKED)' in dyn,'.gnu.prelink_undo':'.gnu.prelink_undo' in sec}
  state['tvs_markers']=markers
  gate=markers['GNU_LIBLIST'] and (markers['.gnu.prelink_undo'] if ALLOW_UNDO else markers['GNU_PRELINKED'])
  if not gate:raise RuntimeError('tvs_prelink_marker_gate_failed')
  state['status']='PASS';log('preflight PASS')
 except BaseException as e:
  state['status']='FAILED';state['reason']=str(e);log('preflight FAILED '+str(e))
  raise
 finally:
  (HERE/'preflight.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException:
  status='失败';raise
 finally:print('已结束',stamp(),'状态='+status,flush=True)
