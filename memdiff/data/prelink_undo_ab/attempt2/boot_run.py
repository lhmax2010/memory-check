#!/usr/bin/env python3
"""One cold-start memcheck trial with identity, health, loader and pagemap gates."""
import argparse, gzip, json, os, re, subprocess, sys, time
from pathlib import Path
import preflight as p

HERE=p.HERE
STAGE='/opt/usr/prelink_ab_stage'
NEEDED=['tvs-daemon','tv-viewer','avocd','amd','launchpad-loader','launchpad-process-pool','pulseaudio','rscmgr-service','acm-service','boot-helper-dyboost-tv']
REFUSAL=re.compile(r'NOT signed|(?:k?UEP|signature|signing|integrity).{0,100}(?:fail|reject|deny|refus|not signed)',re.I)

def record(folder,name,cmd,timeout=120):
 rc,out,err=p.board(name,cmd,timeout)
 (folder/(name+'.stdout')).write_text(out)
 (folder/(name+'.stderr')).write_text(err)
 (folder/(name+'.rc')).write_text(str(rc)+'\n')
 return rc,out,err

def identity(folder,name):
 cmds={'arch':'uname -m','model':'cat /proc/device-tree/model','cmdline':'cat /proc/cmdline','version':'cat /proc/version','build':"sed -n 's/^BUILD_ID=//p' /etc/os-release",'boot_id':'cat /proc/sys/kernel/random/boot_id','uptime':'cat /proc/uptime'}
 fields={}
 for key,cmd in cmds.items():
  rc,out,_=record(folder,name+'_'+key,cmd)
  if rc:raise RuntimeError(f'identity {key} rc={rc}')
  fields[key]=out.replace('\x00','').strip()
 checks={'armv7l':fields['arch']=='armv7l','NT72671D':'NT72671D' in fields['model'],'KSU2E':bool(re.search(r'dtsversion=\S*KSU2E',fields['cmdline'])),'GCC_kernel':'gcc' in fields['version'].lower(),'BUILD_ID':fields['build']==p.BUILD,'boot_id':bool(fields['boot_id'])}
 (folder/(name+'_identity.json')).write_text(json.dumps({'fields':fields,'checks':checks},ensure_ascii=False,indent=2)+'\n')
 if not all(checks.values()):raise RuntimeError('identity gate failed '+str(checks))
 return fields

def root_on(folder,tag):
 rc,_,_=p.run(tag+'_root_on',[p.SDB,'-s',p.IP,'root','on'])
 if rc:raise RuntimeError('root on failed')
 rc,uid,_=record(folder,tag+'_uid','id -u')
 if rc or uid.strip()!='0':raise RuntimeError('root UID missing')

def root_off(folder,tag):
 rc,_,_=p.run(tag+'_root_off',[p.SDB,'-s',p.IP,'root','off'])
 rc2,uid,_=record(folder,tag+'_sdk_uid','id -u')
 if rc or rc2 or uid.strip()=='0':raise RuntimeError('root off failed')

def reboot(folder,tag):
 old=identity(folder,tag+'_before')['boot_id']
 root_on(folder,tag+'_before_reboot')
 # SDB's top-level reboot command is unsupported on this device. A root
 # shell reboot disconnects transport, so its return code is evidence only;
 # the changed boot ID below is the actual success gate.
 rc,_,_=p.board(tag+'_reboot','reboot',30)
 p.log(tag+f' reboot transport/remote result={rc}; awaiting changed boot ID')
 deadline=time.monotonic()+900
 n=0
 while time.monotonic()<deadline:
  time.sleep(15);n+=1
  rc,_,_=p.run(tag+f'_connect_{n:02d}',[p.SDB,'connect',p.IP],20)
  if rc:continue
  rc,boot,_=record(folder,tag+f'_boot_probe_{n:02d}','cat /proc/sys/kernel/random/boot_id')
  if rc==0 and boot.strip() and boot.strip()!=old:
   fields=identity(folder,tag+'_after')
   if fields['boot_id']!=boot.strip():raise RuntimeError('boot ID changed during identity')
   p.log(tag+' RECONNECTED new boot ID='+fields['boot_id'])
   return fields
 raise RuntimeError('board did not reconnect with a changed boot ID within 15 min')

def process_health(ps):
 lines=[x for x in ps.splitlines() if 'ps -eo' not in x]
 status={}
 for name in NEEDED:
  rx=re.compile(r'(?<![A-Za-z0-9_-])'+re.escape(name)+r'(?:\.sh)?(?![A-Za-z0-9_-])')
  status[name]=any(rx.search(x) for x in lines)
 return status

def health(folder,tag,reference=None):
 deadline=time.monotonic()+600
 n=0
 while True:
  n+=1
  rc,up,_=record(folder,tag+f'_uptime_{n:02d}',"awk '{print int($1)}' /proc/uptime")
  if rc:raise RuntimeError('uptime failed')
  sec=int(up.strip())
  rc,ps,_=record(folder,tag+f'_ps_{n:02d}','ps -eo pid,ppid,comm,args')
  if rc:raise RuntimeError('ps failed')
  present=process_health(ps)
  if sec>=180 and all(present.values()):break
  if time.monotonic()>=deadline:break
  p.log(f'{tag} health wait uptime={sec} missing={[x for x,y in present.items() if not y]}')
  time.sleep(30)
 rc,failed,_=record(folder,tag+'_failed_units','systemctl --failed --no-legend --plain')
 if rc:raise RuntimeError('systemctl --failed failed')
 record(folder,tag+'_amd_activation_units','systemctl show -p ActiveState -p SubState ac.service ac.socket amd-tizen-action-service.socket')
 failed_set=sorted({x.split()[0] for x in failed.splitlines() if x.strip() and not x.startswith('__')})
 extra=[] if reference is None else sorted(set(failed_set)-set(reference))
 rc,dmesg,_=record(folder,tag+'_dmesg','dmesg',180)
 if rc:raise RuntimeError('dmesg failed')
 _,main,_=record(folder,tag+'_dlog_main','dlogutil -d -b main',180)
 _,system,_=record(folder,tag+'_dlog_system','dlogutil -d -b system',180)
 refusals=[x for src,text in [('dmesg',dmesg),('dlog_main',main),('dlog_system',system)] for x in text.splitlines() if REFUSAL.search(x)]
 (folder/'signature_refusals.txt').write_text('\n'.join(refusals)+'\n')
 quality={'uptime_s':sec,'processes':present,'failed_units':failed_set,'new_failed_units':extra,'signature_refusal_lines':len(refusals),'healthy':all(present.values()) and not extra and not refusals}
 (folder/'health.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2)+'\n')
 p.log(f'{tag} HEALTH {quality["healthy"]} uptime={sec} missing={[x for x,y in present.items() if not y]} new_failed={extra} refusals={len(refusals)}')
 return quality

def diagnostic(folder,tag):
 rc,out,_=record(folder,tag+'_prelink_diag','LD_DEBUG=libs /usr/bin/pulseaudio --version',60)
 matches=[x for x in out.splitlines() if 'prelink checking' in x.lower() or 'vdprelink' in x.lower() or 'not prelinked' in x.lower()]
 (folder/'prelink_diagnostic.json').write_text(json.dumps({'rc':rc,'lines':matches,'has_ok':any('prelink checking: ok' in x.lower() for x in matches),'has_not_prelinked':any('not prelinked' in x.lower() for x in matches)},ensure_ascii=False,indent=2)+'\n')
 p.log(tag+' PRELINK_DIAG '+str(matches[:3]))

def pagemap(folder,tag):
 out=folder/'pagemap13';out.mkdir(exist_ok=True)
 env=os.environ.copy();env['PRELINK_PAGEMAP_OUT']=str(out.resolve())
 root_off(folder,tag+'_for_pagemap')
 try:
  q=subprocess.run([sys.executable,str(HERE/'pagemap13_collector.py'),p.IP],stdin=subprocess.DEVNULL,capture_output=True,env=env,timeout=600)
  (folder/'pagemap13_console.stdout').write_bytes(q.stdout)
  (folder/'pagemap13_console.stderr').write_bytes(q.stderr)
  (folder/'pagemap13_rc.txt').write_text(str(q.returncode)+'\n')
  p.log(f'{tag} PAGEMAP13 rc={q.returncode}')
  if q.returncode:raise RuntimeError('13-object pagemap collection failed')
 finally:root_on(folder,tag+'_after_pagemap')

def memcheck(folder,tag,first_boot):
 rc,out,_=record(folder,tag+'_memcheck_launch',f'body=$(cat {STAGE}/memcheck.sh); [ -n "$body" ] || exit 42; bash -c "$body" memcheck gcc',120)
 if rc:raise RuntimeError('memcheck launch failed')
 m=re.search(r'后台采集已启动：(\S+)',out)
 if not m:raise RuntimeError('memcheck output directory missing')
 remote_dir=m.group(1)
 (folder/'remote_result_dir.txt').write_text(remote_dir+'\n')
 p.log(tag+' MEMCHECK '+remote_dir)
 deadline=time.monotonic()+3600
 collected=False;n=0
 while time.monotonic()<deadline:
  time.sleep(30);n+=1
  rc,status,_=record(folder,tag+f'_poll_{n:03d}',f'cat {remote_dir}/STATUS')
  if rc:raise RuntimeError('memcheck STATUS unreadable')
  value=status.strip()
  if first_boot and not collected:
   rc_ready,_,_=record(folder,tag+f'_snap_ready_{n:03d}',f"grep -q '步骤 4/6' {remote_dir}/run.log")
   if rc_ready==0:
    pagemap(folder,tag);collected=True
  if n%10==0:p.log(f'{tag} MEMCHECK poll={n} status={value}')
  if value in ('DONE','FAILED'):break
 else:raise RuntimeError('memcheck exceeded 60 min')
 if value!='DONE':raise RuntimeError('memcheck STATUS '+value)
 p.log(tag+' MEMCHECK DONE')
 destination=folder/'memcheck_pull';destination.mkdir(exist_ok=True)
 rc,_,_=p.run(tag+'_pull_memcheck',[p.SDB,'-s',p.IP,'pull',remote_dir,str(destination)],1800)
 if rc:raise RuntimeError('memcheck pull failed')
 matches=list(destination.rglob('02_steady/smaps_raw.txt.gz'))
 if len(matches)!=1:raise RuntimeError('steady smaps missing after pull')
 with gzip.open(matches[0],'rb') as f:
  while f.read(1024*1024):pass
 (folder/'local_result_dir.txt').write_text(str(matches[0].parents[1])+'\n')
 p.log(tag+' MEMCHECK pulled and gzip checked')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('state',choices=('factory','programs_undone','all_undone'));parser.add_argument('index',type=int,choices=(1,2));args=parser.parse_args()
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 if not (HERE/'stage_complete.json').is_file():raise RuntimeError('stage not complete')
 tag=f'{args.state}_{args.index}'
 folder=HERE/'boots'/tag;folder.mkdir(parents=True,exist_ok=False)
 root=False
 try:
  fields=reboot(folder,tag)
  root=True;root_on(folder,tag)
  reference=None
  base=HERE/'boots/factory_1/health.json'
  if tag!='factory_1':
   if not base.is_file():raise RuntimeError('factory health reference absent')
   reference=json.loads(base.read_text())['failed_units']
  quality=health(folder,tag,reference)
  if not quality['healthy']:raise RuntimeError('health gate failed')
  diagnostic(folder,tag)
  memcheck(folder,tag,args.index==1)
  record(folder,tag+'_post_dmesg','dmesg',180)
  record(folder,tag+'_post_dlog_main','dlogutil -d -b main',180)
  record(folder,tag+'_post_dlog_system','dlogutil -d -b system',180)
  (folder/'boot_result.json').write_text(json.dumps({'state':args.state,'index':args.index,'boot_id':fields['boot_id'],'status':'DONE','health':quality},ensure_ascii=False,indent=2)+'\n')
  p.log(tag+' DONE')
 finally:
  if root:root_off(folder,tag)

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
