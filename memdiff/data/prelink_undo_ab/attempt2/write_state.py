#!/usr/bin/env python3
"""Apply or restore prelink A/B bytes with durable per-file evidence.

Never unlinks or renames a system ELF. Every remote shell result is recorded
by preflight.board. Invoke restore after any partial apply.
"""
import argparse, csv, json, os, re, sys
from pathlib import Path
import preflight as p

HERE=p.HERE
STAGE='/opt/usr/prelink_ab_stage'
TOOLS='/root/prelink_ab_tools'
UPPER='/opt/.overlay/platform/upperdir'
TOUCHED=HERE/'touched_paths.jsonl'

def q(s):
 return "'"+s.replace("'","'\\''")+"'"

def board(name,cmd,timeout=120):
 rc,out,err=p.board(name,cmd,timeout)
 if rc:raise RuntimeError(f'{name} remote rc={rc}: {err[-300:]} {out[-300:]}')
 return out

def root_on():
 rc,_,_=p.run('write_root_on',[p.SDB,'-s',p.IP,'root','on'])
 if rc or board('write_root_uid','id -u').strip()!='0':raise RuntimeError('root on failed')

def root_off():
 rc,_,_=p.run('write_root_off',[p.SDB,'-s',p.IP,'root','off'])
 rc2,uid,_=p.board('write_sdk_uid','id -u')
 if rc or rc2 or uid.strip()!='5001':raise RuntimeError('root off failed')

def selected(category):
 with (HERE/'pull_classify.tsv').open() as f:
  return [r for r in csv.DictReader(f,delimiter='\t') if r['selected']=='1' and r['category']==category]

def metadata():
 return {x['path']:x for x in map(json.loads,(HERE/'metadata.jsonl').read_text().splitlines())}

def xattrs(s):
 return sorted(x.strip() for x in s.splitlines() if re.match(r'^[A-Za-z][A-Za-z0-9_.-]*=',x.strip()))

def canonical_chsmack(s):
 return re.sub(r'^\S+\s+','',s.strip())

def inspect(path,tag):
 esc=q(path)
 cmds={
  'sha':f'sha256sum {esc}',
  'stat':f'stat -c "%u %g %a %s" {esc}',
  'xattrs':f'{TOOLS}/getfattr -d -m - -e hex {esc}',
  'getcap':f'getcap {esc}',
  'chsmack':f'chsmack {esc}',
  'upper':f'test -f {q(UPPER+path)}',
 }
 result={}
 for key,cmd in cmds.items():
  rc,out,err=p.board(f'{tag}_{key}',cmd)
  result[key]={'rc':rc,'stdout':out,'stderr':err}
 if any(result[k]['rc'] for k in ('sha','stat','xattrs','getcap','chsmack')):
  raise RuntimeError('post-write metadata read failed '+path)
 return result

def compare(path,got,expected_sha,base,require_upper=True):
 errs=[]
 if got['sha']['stdout'].split()[0]!=expected_sha:errs.append('sha256')
 if got['stat']['stdout'].split()[:3]!=base['commands']['stat']['stdout'].split()[:3]:errs.append('owner/mode')
 if xattrs(got['xattrs']['stdout'])!=xattrs(base['commands']['xattrs']['stdout']):errs.append('xattrs')
 if got['getcap']['stdout'].strip()!=base['commands']['getcap']['stdout'].strip():errs.append('getcap')
 if canonical_chsmack(got['chsmack']['stdout'])!=canonical_chsmack(base['commands']['chsmack']['stdout']):errs.append('chsmack')
 if require_upper and got['upper']['rc']!=0:errs.append('overlay upper absent')
 return errs

def restore_metadata(path,base,tag):
 stat=base['commands']['stat']['stdout'].split()
 if len(stat)<3:raise RuntimeError('baseline stat malformed '+path)
 board(tag+'_chown',f'chown {stat[0]}:{stat[1]} {q(path)}')
 board(tag+'_chmod',f'chmod {stat[2]} {q(path)}')
 desired=dict(x.split('=',1) for x in xattrs(base['commands']['xattrs']['stdout']))
 current=inspect(path,tag+'_before_xattr_restore')
 present=dict(x.split('=',1) for x in xattrs(current['xattrs']['stdout']))
 for key in sorted(set(present)-set(desired)):
  board(tag+'_remove_'+key,f'{TOOLS}/setfattr -x {q(key)} {q(path)}')
 for key,val in desired.items():
  if present.get(key)!=val:
   board(tag+'_set_'+key,f'{TOOLS}/setfattr -n {q(key)} -v {q(val)} {q(path)}')

def write_one(path,variant,tag,expected_sha,base):
 stage=f'{STAGE}/{variant}{path}'
 actual=board(tag+'_stage_sha',f'sha256sum {q(stage)}').split()[0]
 if actual!=expected_sha:raise RuntimeError('staged SHA mismatch '+path)
 with TOUCHED.open('a') as f:
  f.write(json.dumps({'path':path,'variant':variant,'time':p.now()},ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 rc,out,err=p.board(tag+'_copy',f'cat {q(stage)} > {q(path)}',180)
 if rc:
  if 'Text file busy' in out+err:
   # Stop only the exact system unit owning a mapped executable. If ownership
   # is ambiguous, leave the file alone and let the caller restore everything.
   name=Path(path).name
   rc_ps,ps,_=p.board(tag+'_busy_ps',f'ps -eo pid,ppid,comm,args | grep -F {q(name)}')
   units=set()
   if rc_ps==0:
    for line in ps.splitlines():
     if path not in line:continue
     fields=line.split()
     if not fields or not fields[0].isdigit():continue
     _,cg,_=p.board(tag+'_busy_cgroup_'+fields[0],f'cat /proc/{fields[0]}/cgroup')
     for match in re.findall(r'([A-Za-z0-9_.@-]+\.service)',cg):
      units.add(match)
   (HERE/(tag+'_busy_units.json')).write_text(json.dumps({'path':path,'units':sorted(units),'ps':ps},indent=2)+'\n')
   if len(units)==1:
    unit=next(iter(units))
    # SDB has a short per-command response timeout; systemctl's blocking stop
    # can exceed it. Queue the stop and poll the exact executable until gone.
    board(tag+'_stop_unit_nonblocking',f'systemctl stop --no-block {q(unit)}',30)
    stopped=False
    for attempt in range(1,25):
     rc_pid,pid_out,_=p.board(tag+f'_stop_poll_{attempt:02d}',f'pidof {q(name)}')
     if rc_pid!=0 or not pid_out.strip():stopped=True;break
     import time;time.sleep(5)
    if not stopped:raise RuntimeError('unit did not release executable within 120 s: '+unit)
    rc,out,err=p.board(tag+'_copy_after_stop',f'cat {q(stage)} > {q(path)}',180)
   elif not units and path in (
      '/usr/apps/org.tizen.tv-viewer/bin/tv-viewer',
      '/usr/bin/launchpad-loader',
      '/usr/bin/launchpad-process-pool'):
    # Some Tizen applications are launched by launchpad and live in init.scope,
    # with no owning systemd unit. Stop only the exact mapped executable with
    # SIGTERM; cold boot, not a manual restart, restores the normal app state.
    pids=[]
    for line in ps.splitlines():
     f=line.split()
     if not f or not f[0].isdigit() or path not in line:continue
     pid=f[0]
     rc_exe,exe,_=p.board(tag+'_app_exe_'+pid,f'readlink -f /proc/{pid}/exe')
     if rc_exe==0 and exe.strip()==path:pids.append(pid)
    if not pids:raise RuntimeError('no exact executable PID for app '+path)
    (HERE/(tag+'_app_sigterm.json')).write_text(json.dumps({'path':path,'pids':pids,'signal':'TERM','time':p.now()},indent=2)+'\n')
    for pid in pids:board(tag+'_app_term_'+pid,f'kill -TERM {pid}')
    stopped=False
    for attempt in range(1,13):
     rc_pid,pid_out,_=p.board(tag+f'_app_poll_{attempt:02d}',f'pidof {q(name)}')
     if rc_pid!=0 or not pid_out.strip():stopped=True;break
     import time;time.sleep(5)
    if not stopped:raise RuntimeError('app did not exit within 60 s: '+path)
    rc,out,err=p.board(tag+'_copy_after_app_term',f'cat {q(stage)} > {q(path)}',180)
  if rc:raise RuntimeError(f'copy failed {path} rc={rc}: {err[-300:]} {out[-300:]}')
 got=inspect(path,tag+'_post')
 errs=compare(path,got,expected_sha,base)
 if errs:
  restore_metadata(path,base,tag+'_fixattrs')
  got=inspect(path,tag+'_postfix')
  errs=compare(path,got,expected_sha,base)
 if errs:raise RuntimeError('post-write gate '+path+' '+','.join(errs))
 p.log(f'WRITE_OK {variant} {path}')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=('programs','libraries','restore'));args=ap.parse_args()
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 baselines=metadata()
 undo={r['path']:r for r in csv.DictReader((HERE/'undo_attempt2.tsv').open(),delimiter='\t')}
 root=False
 try:
  root=True;root_on()
  if args.action!='restore':
   board('write_tools_getfattr_ready',f'{TOOLS}/getfattr --version')
   board('write_tools_setfattr_ready',f'{TOOLS}/setfattr --version')
   board('write_stage_ready',f'test -d {STAGE}/original -a -d {STAGE}/undo')
  if args.action=='restore':
   if not TOUCHED.is_file():
    p.log('No touched paths; restore is vacuous');return
   paths=list(dict.fromkeys(x['path'] for x in map(json.loads,TOUCHED.read_text().splitlines())))
   for i,path in enumerate(reversed(paths),1):
    base=baselines[path];tag=f'restore_{i:03d}'
    expected=undo[path]['before_sha256']
    current=inspect(path,tag+'_before')
    if not compare(path,current,expected,base,require_upper=False):
     p.log('RESTORE_ALREADY_OK '+path);continue
    write_one(path,'original',tag,expected,base)
   (HERE/'restore_complete.json').write_text(json.dumps({'time':p.now(),'paths':len(paths),'status':'DONE'},indent=2)+'\n')
  else:
   cat='program' if args.action=='programs' else 'library'
   rows=selected(cat)
   done=set(x['path'] for x in map(json.loads,TOUCHED.read_text().splitlines())) if TOUCHED.is_file() else set()
   for i,row in enumerate(rows,1):
    path=row['path']
    if path in done:raise RuntimeError('path already touched in this experiment: '+path)
    if path not in baselines or path not in undo:raise RuntimeError('missing baseline '+path)
    write_one(path,'undo',f'{args.action}_{i:03d}',undo[path]['after_sha256'],baselines[path])
   (HERE/(args.action+'_apply_complete.json')).write_text(json.dumps({'time':p.now(),'count':len(rows),'status':'DONE'},indent=2)+'\n')
 finally:
  if root:root_off()

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
