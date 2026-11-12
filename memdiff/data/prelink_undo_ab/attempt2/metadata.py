#!/usr/bin/env python3
"""Record exact ownership, mode, all xattrs, capabilities and SMACK for targets."""
import csv, json, os, re, shlex, subprocess, sys
from pathlib import Path
import preflight as p

HERE=p.HERE
STAGE='/root/prelink_ab_tools'
TOOLS=Path('/tmp/prelink_undo_attr/usr/bin')

def remote(cmd):
 wrapped=cmd+"; __ab_rc=$?; printf '\\n__AB_RC__%d\\n' \"$__ab_rc\""
 q=subprocess.run([p.SDB,'-s',p.IP,'shell',wrapped],stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
 out=q.stdout.decode(errors='replace');err=q.stderr.decode(errors='replace')
 m=re.search(r'\n__AB_RC__(\d+)\s*$',out)
 rc=q.returncode or (int(m.group(1)) if m else 255)
 return rc,out[:m.start()] if m else out,err

def main():
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 rows=list(csv.DictReader((HERE/'pull_classify.tsv').open(),delimiter='\t'))
 paths=[r['path'] for r in rows if r['selected']=='1']
 if not paths:raise RuntimeError('no selected files')
 root=False;stage=False
 try:
  rc,_,_=p.run('metadata_root_on',[p.SDB,'-s',p.IP,'root','on'])
  if rc:raise RuntimeError('root on failed')
  root=True
  rc,uid,_=p.board('metadata_uid','id -u')
  if rc or uid.strip()!='0':raise RuntimeError('root UID missing')
  rc,_,_=p.board('metadata_stage_absent',f'test ! -e {STAGE}')
  if rc:raise RuntimeError('stage exists')
  rc,_,_=p.board('metadata_stage_create',f'mkdir -m 700 {STAGE}')
  if rc:raise RuntimeError('stage mkdir failed')
  stage=True
  for n in ('getfattr','setfattr'):
   rc,_,_=p.run('metadata_push_'+n,[p.SDB,'-s',p.IP,'push',str(TOOLS/n),f'{STAGE}/{n}'],120)
   if rc:raise RuntimeError('tool push failed '+n)
  for n in ('getfattr','setfattr'):
   rc,_,_=p.board('metadata_tool_'+n,f'{STAGE}/{n} --version')
   if rc:raise RuntimeError('tool cannot run '+n)
  with (HERE/'metadata.jsonl').open('w') as f:
   for i,path in enumerate(paths,1):
    q=shlex.quote(path)
    commands={'stat':f"stat -c '%u %g %a %s' {q}",'xattrs':f'{STAGE}/getfattr -d -m - -e hex {q}','getcap':f'/usr/sbin/getcap -n {q}','chsmack':f'chsmack {q}'}
    result={'path':path,'commands':{}}
    for n,cmd in commands.items():
     rc,out,err=remote(cmd)
     result['commands'][n]={'rc':rc,'stdout':out,'stderr':err}
    result['all_readable']=all(v['rc']==0 for v in result['commands'].values())
    f.write(json.dumps(result,ensure_ascii=False)+'\n');f.flush()
    if i%25==0 or i==len(paths):p.log(f'METADATA {i}/{len(paths)}')
 finally:
  if root:
   if stage:p.board('metadata_stage_cleanup',f'rm -f {STAGE}/getfattr {STAGE}/setfattr; rmdir {STAGE}; test ! -e {STAGE}')
   p.run('metadata_root_off',[p.SDB,'-s',p.IP,'root','off'])
   rc,uid,_=p.board('metadata_sdk_uid','id -u')
   if rc or uid.strip()=='0':raise RuntimeError('sdb root off failed')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
