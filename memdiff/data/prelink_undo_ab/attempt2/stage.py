#!/usr/bin/env python3
"""Stage verified original/undone copies and memcheck payload; no system ELF writes."""
import csv, hashlib, json, os, re, subprocess, sys, tarfile
from pathlib import Path
import preflight as p

HERE=p.HERE
STAGE='/opt/usr/prelink_ab_stage'
TOOLS='/root/prelink_ab_tools'
SRC=Path('memdiff/scripts/memcheck_runtime.sh')
ATTR=Path('/tmp/prelink_undo_attr/usr/bin')

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def payload():
 text=SRC.read_text()
 old=sha(SRC)
 edits=[('SCRIPT=/opt/usr/memcheck/memcheck.sh',f'SCRIPT={STAGE}/memcheck.sh'),('BASE=/opt/usr/memcheck',f'BASE={STAGE}/memcheck'),('STEADY_CPU_BUSY_MAX=20', 'STEADY_CPU_BUSY_MAX=21'),('STEADY_TIMEOUT=2700','STEADY_TIMEOUT=1800'),('ab>=cb','ab>cb')]
 for a,b in edits:
  if text.count(a)!=1:raise RuntimeError('payload edit count incorrect: '+a)
  text=text.replace(a,b)
 out=HERE/'memcheck_ab.sh';out.write_text(text)
 q=subprocess.run(['bash','-n',str(out)],stdin=subprocess.DEVNULL,capture_output=True)
 if q.returncode:raise RuntimeError('payload bash -n failed '+q.stderr.decode())
 (HERE/'payload_provenance.json').write_text(json.dumps({'original_path':str(SRC),'original_sha256':old,'payload_sha256':sha(out),'edits':edits},ensure_ascii=False,indent=2)+'\n')
 return out

def main():
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 rows=list(csv.DictReader((HERE/'pull_classify.tsv').open(),delimiter='\t'))
 undo={r['path']:r for r in csv.DictReader((HERE/'undo_attempt2.tsv').open(),delimiter='\t')}
 meta={x['path']:x for x in (json.loads(s) for s in (HERE/'metadata.jsonl').open())}
 selected=[r for r in rows if r['selected']=='1']
 if len(selected)!=434 or any(undo[r['path']]['status']!='success' or not meta[r['path']]['all_readable'] for r in selected):
  raise RuntimeError('selected/undo/metadata gate incomplete')
 total=sum(int(r['bytes']) for r in selected)
 payload_file=payload()
 rc,out,_=p.board('stage_space_before','df -Pk /opt/usr /opt/.overlay/platform/upperdir')
 if rc:raise RuntimeError('space command failed')
 available=[int(x.split()[3]) for x in out.splitlines() if x.startswith('/dev/')]
 if len(available)<2 or min(available)*1024<=2*total:
  raise RuntimeError(f'free space insufficient: {available}, 2x target bytes={2*total}')
 manifest={'selected_files':len(selected),'original_total_bytes':total,'min_free_kib':min(available),'required_free_kib':(2*total+1023)//1024,'stage_path':STAGE,'tools_path':TOOLS}
 (HERE/'stage_space_gate.json').write_text(json.dumps(manifest,indent=2)+'\n')
 tarpath=HERE/'stage_payload.tar'
 with tarfile.open(tarpath,'w') as tar:
  tar.add(payload_file,arcname='memcheck.sh',recursive=False)
  for i,r in enumerate(selected,1):
   rel=r['path'].lstrip('/')
   tar.add(HERE/'pulled_root'/rel,arcname='original/'+rel,recursive=False)
   tar.add(HERE/'undo_root'/rel,arcname='undo/'+rel,recursive=False)
   if i%25==0 or i==len(selected):p.log(f'PACK {i}/{len(selected)}')
 manifest['tar_bytes']=tarpath.stat().st_size;manifest['tar_sha256']=sha(tarpath)
 (HERE/'stage_space_gate.json').write_text(json.dumps(manifest,indent=2)+'\n')
 root=False;stage_created=False;tools_created=False
 try:
  rc,_,_=p.run('stage_root_on',[p.SDB,'-s',p.IP,'root','on'])
  if rc:raise RuntimeError('root on failed')
  root=True
  rc,uid,_=p.board('stage_uid','id -u')
  if rc or uid.strip()!='0':raise RuntimeError('root UID missing')
  for path in (STAGE,TOOLS):
   rc,_,_=p.board('stage_absent_'+path.split('/')[-1],f'test ! -e {path}')
   if rc:raise RuntimeError('stage path already exists: '+path)
  rc,_,_=p.board('stage_mkdir',f'mkdir -m 700 {STAGE} {TOOLS}')
  if rc:raise RuntimeError('stage mkdir failed')
  stage_created=tools_created=True
  rc,_,_=p.run('stage_push_tar',[p.SDB,'-s',p.IP,'push',str(tarpath),f'{STAGE}/payload.tar'],1800)
  if rc:raise RuntimeError('tar push failed')
  rc,out,_=p.board('stage_tar_sha',f'sha256sum {STAGE}/payload.tar',120)
  if rc or not out.startswith(manifest['tar_sha256']):raise RuntimeError('board tar SHA mismatch')
  rc,_,_=p.board('stage_extract',f'tar xf {STAGE}/payload.tar -C {STAGE}',600)
  if rc:raise RuntimeError('board tar extract failed')
  rc,_,_=p.board('stage_remove_tar',f'rm -f {STAGE}/payload.tar; test ! -e {STAGE}/payload.tar')
  if rc:raise RuntimeError('stage tar cleanup failed')
  for name in ('getfattr','setfattr'):
   rc,_,_=p.run('stage_push_'+name,[p.SDB,'-s',p.IP,'push',str(ATTR/name),f'{TOOLS}/{name}'],120)
   if rc:raise RuntimeError('attr push failed '+name)
   rc,_,_=p.board('stage_check_'+name,f'{TOOLS}/{name} --version')
   if rc:raise RuntimeError('attr execution failed '+name)
  rc,out,_=p.board('stage_payload_sha',f'sha256sum {STAGE}/memcheck.sh')
  if rc or not out.startswith(sha(payload_file)):raise RuntimeError('board payload SHA mismatch')
  rc,space_after,_=p.board('stage_space_after','df -Pk /opt/usr /opt/.overlay/platform/upperdir')
  if rc:raise RuntimeError('space after failed')
  (HERE/'stage_complete.json').write_text(json.dumps({'time':p.now(),'stage':STAGE,'tools':TOOLS,'space_after':space_after,'tar_sha256':manifest['tar_sha256'],'status':'DONE'},ensure_ascii=False,indent=2)+'\n')
  p.log('STAGE DONE')
 finally:
  if root:
   if not (HERE/'stage_complete.json').is_file():
    if tools_created:p.board('stage_cleanup_failed_tools',f'rm -f {TOOLS}/getfattr {TOOLS}/setfattr; rmdir {TOOLS}')
    if stage_created:p.board('stage_cleanup_failed_payload',f'rm -rf {STAGE}; test ! -e {STAGE}',600)
   p.run('stage_root_off',[p.SDB,'-s',p.IP,'root','off'])
   rc,uid,_=p.board('stage_sdk_uid','id -u')
   if rc or uid.strip()=='0':raise RuntimeError('sdb root off failed')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
