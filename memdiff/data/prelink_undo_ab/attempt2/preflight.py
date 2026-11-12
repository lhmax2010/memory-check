#!/usr/bin/env python3
"""Read-only identity, ELF marker, and health preflight for the GCC A/B run."""
import hashlib, json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
RAW=HERE/'raw'; RAW.mkdir(parents=True,exist_ok=True)
IP=os.environ.get('PRELINK_BOARD_IP','')
SDB='/home/linhao/tizen-studio/tools/sdb'
READELF='/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf'
BUILD='T-KSU2EJAKUC-0101-PERF-202610010416'

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def log(s):
 line=f'{now()} {s}'; print(line,flush=True)
 with (HERE/'progress.log').open('a') as f:f.write(line+'\n')
def run(name,args,timeout=120):
 log('RUN '+name)
 try:
  p=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
  rc,out,err=p.returncode,p.stdout,p.stderr
 except subprocess.TimeoutExpired as e:
  rc,out,err=124,e.stdout or b'',(e.stderr or b'')+b'\nTIMEOUT\n'
 (RAW/(name+'.stdout')).write_bytes(out);(RAW/(name+'.stderr')).write_bytes(err)
 (RAW/(name+'.json')).write_text(json.dumps({'time':now(),'argv':args,'transport_rc':rc,'stdout_bytes':len(out),'stderr_bytes':len(err)},ensure_ascii=False,indent=2)+'\n')
 log(f'END {name} rc={rc} bytes={len(out)}')
 return rc,out.decode(errors='replace'),err.decode(errors='replace')
def board(name,cmd,timeout=120):
 wrapped=cmd+"; __ab_rc=$?; printf '\\n__AB_RC__%d\\n' \"$__ab_rc\""
 tr,out,err=run(name,[SDB,'-s',IP,'shell',wrapped],timeout)
 m=re.search(r'\n__AB_RC__(\d+)\s*$',out)
 return (tr or 255,out,err) if not m else (int(m.group(1)),out[:m.start()],err)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 if not IP:raise RuntimeError('PRELINK_BOARD_IP required')
 rc,_,_=run('connect',[SDB,'connect',IP],30)
 if rc:raise RuntimeError('sdb connect failed')
 cmd="printf '__ARCH__\\n'; uname -m; printf '__MODEL__\\n'; cat /proc/device-tree/model; printf '\\n__CMDLINE__\\n'; cat /proc/cmdline; printf '__VERSION__\\n'; cat /proc/version; printf '__BUILD__\\n'; sed -n 's/^BUILD_ID=//p' /etc/os-release; printf '__BOOTID__\\n'; cat /proc/sys/kernel/random/boot_id; printf '__UID__\\n'; id -u"
 rc,out,_=board('identity',cmd)
 fields={}
 for n in ('ARCH','MODEL','CMDLINE','VERSION','BUILD','BOOTID','UID'):
  m=re.search(r'__'+n+r'__\s*\n(.*?)(?=__[A-Z]+__|\Z)',out,re.S)
  fields[n]=m.group(1).strip().replace('\x00','') if m else ''
 checks={'remote_rc':rc==0,'armv7l':fields['ARCH']=='armv7l','model':'NT72671D' in fields['MODEL'],'dtsversion':bool(re.search(r'dtsversion=\S*KSU2E',fields['CMDLINE'])),'gcc_kernel':'gcc' in fields['VERSION'].lower(),'BUILD_ID':fields['BUILD']==BUILD,'boot_id':bool(fields['BOOTID']),'sdk_uid':fields['UID']=='5001'}
 (HERE/'identity.json').write_text(json.dumps({'fields':fields,'checks':checks},ensure_ascii=False,indent=2)+'\n')
 if not all(checks.values()):raise RuntimeError('identity gate failed '+str(checks))
 local=HERE/'tvs-daemon.board'
 rc,_,_=run('pull_tvs',[SDB,'-s',IP,'pull','/usr/bin/tvs-daemon',str(local)],120)
 if rc or not local.is_file():raise RuntimeError('tvs pull failed')
 rc,bsha,_=board('board_tvs_sha','sha256sum /usr/bin/tvs-daemon')
 if rc or bsha.split()[0]!=sha(local):raise RuntimeError('board/host tvs hash mismatch')
 for mode in ('-SW','-dW'):
  rc,_,_=run('tvs_'+mode.replace('-',''),[READELF,mode,str(local)])
  if rc:raise RuntimeError('readelf failed')
 sec=(RAW/'tvs_SW.stdout').read_text();dyn=(RAW/'tvs_dW.stdout').read_text()
 markers={'GNU_LIBLIST':'(GNU_LIBLIST)' in dyn,'.gnu.prelink_undo':'.gnu.prelink_undo' in sec}
 (HERE/'tvs_gate.json').write_text(json.dumps({'board_sha256':bsha.split()[0],'host_sha256':sha(local),'markers':markers},indent=2)+'\n')
 if not all(markers.values()):raise RuntimeError('tvs marker gate failed')
 board('prelink_conf','cat /etc/prelink.conf')
 board('space','df -Pk /opt/usr /opt/.overlay/platform/upperdir')
 board('failed_units','systemctl --failed --no-legend --plain')
 board('processes','ps -eo pid,ppid,comm,args',120)
 log('PREFLIGHT PASS')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:
  status='失败';log('ERROR '+repr(e));raise
 finally:print('已结束',now(),'状态='+status,flush=True)
