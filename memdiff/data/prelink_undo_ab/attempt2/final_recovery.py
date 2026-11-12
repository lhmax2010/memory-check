#!/usr/bin/env python3
"""Verify restored bytes, reboot, compare factory health, clean owned staging."""
import csv, json, os
from pathlib import Path
import preflight as p
import boot_run as b
from write_state import inspect, compare, metadata

HERE=p.HERE
FOLDER=HERE/'recovery'

def record_inventory(name):
 rc,out,err=p.board(name,"find /opt/.overlay/platform/upperdir/usr -xdev -type f | sort",300)
 (FOLDER/(name+'.stdout')).write_text(out)
 (FOLDER/(name+'.stderr')).write_text(err)
 (FOLDER/(name+'.rc')).write_text(str(rc)+'\n')
 if rc:raise RuntimeError('overlay inventory failed')

def verify_originals():
 m=metadata()
 rows={x['path']:x for x in csv.DictReader((HERE/'undo_attempt2.tsv').open(),delimiter='\t')}
 touched=HERE/'touched_paths.jsonl'
 paths=list(dict.fromkeys(x['path'] for x in map(json.loads,touched.read_text().splitlines()))) if touched.is_file() else []
 errors=[]
 for i,path in enumerate(paths,1):
  got=inspect(path,f'recovery_verify_{i:03d}')
  bad=compare(path,got,rows[path]['before_sha256'],m[path],require_upper=False)
  if bad:errors.append({'path':path,'errors':bad})
 (FOLDER/'original_verify.json').write_text(json.dumps({'count':len(paths),'errors':errors},ensure_ascii=False,indent=2)+'\n')
 if errors:raise RuntimeError(f'{len(errors)} files differ from originals')

def main():
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 FOLDER.mkdir(exist_ok=True)
 root=True;b.root_on(FOLDER,'recovery_precheck')
 try:
  verify_originals()
  record_inventory('overlay_before_recovery_reboot')
 finally:
  if root:b.root_off(FOLDER,'recovery_precheck')
 b.reboot(FOLDER,'recovery')
 root=True;b.root_on(FOLDER,'recovery_postboot')
 post_error=None;health=None;d=None;cleaned=False
 try:
  try:
   base=json.loads((HERE/'boots/factory_1/health.json').read_text())
   health=b.health(FOLDER,'recovery',base['failed_units'])
   b.diagnostic(FOLDER,'recovery')
   d=json.loads((FOLDER/'prelink_diagnostic.json').read_text())
   if not health['healthy']:raise RuntimeError('recovery health differs from factory')
   if not d['has_ok']:raise RuntimeError('prelink diagnosis not restored')
  except BaseException as e:
   post_error=e;p.log('RECOVERY_POSTCHECK_FAILED '+repr(e))
  record_inventory('overlay_after_recovery_reboot')
  rc,_,_=p.board('recovery_cleanup_stage','rm -rf /opt/usr/prelink_ab_stage; test ! -e /opt/usr/prelink_ab_stage',600)
  if rc:raise RuntimeError('stage cleanup failed')
  rc,_,_=p.board('recovery_cleanup_tools','rm -f /root/prelink_ab_tools/getfattr /root/prelink_ab_tools/setfattr; rmdir /root/prelink_ab_tools; test ! -e /root/prelink_ab_tools')
  if rc:raise RuntimeError('tool cleanup failed')
  cleaned=True
  (FOLDER/'recovery_result.json').write_text(json.dumps({'status':'DONE' if post_error is None else 'POSTCHECK_FAILED','health':health,'prelink_diag':d,'stage_cleaned':cleaned,'postcheck_error':repr(post_error) if post_error else None},ensure_ascii=False,indent=2)+'\n')
 finally:
  if root:b.root_off(FOLDER,'recovery_postboot')
 if post_error:raise post_error

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
