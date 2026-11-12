#!/usr/bin/env python3
"""Serial A/B runner; invoke only after factory_1 has completed successfully.

The finally block always tries original-byte restoration and a verification
reboot if any path was touched. All child stdout/stderr are saved verbatim.
"""
import os, subprocess, sys
from pathlib import Path
import preflight as p

HERE=p.HERE

def child(label,args,timeout):
 p.log('PHASE_START '+label)
 with (HERE/(label+'_console.log')).open('w') as log:
  q=subprocess.run([sys.executable,str(HERE/args[0]),*args[1:]],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,env=os.environ.copy())
 p.log(f'PHASE_END {label} rc={q.returncode}')
 if q.returncode:raise RuntimeError(f'{label} failed; see {label}_console.log')

def upper_before():
 rc,_,_=p.run('upper_before_root_on',[p.SDB,'-s',p.IP,'root','on'])
 if rc:raise RuntimeError('root on failed before overlay inventory')
 try:
  rc,out,err=p.board('upper_before',"find /opt/.overlay/platform/upperdir/usr -xdev -type f | sort",300)
  (HERE/'overlay_upper_before.txt').write_text(out)
  (HERE/'overlay_upper_before.stderr').write_text(err)
  if rc:raise RuntimeError('overlay upper inventory failed')
 finally:
  p.run('upper_before_root_off',[p.SDB,'-s',p.IP,'root','off'])
  rc,uid,_=p.board('upper_before_uid','id -u')
  if rc or uid.strip()!='5001':raise RuntimeError('root off not confirmed')

def main():
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 if not (HERE/'boots/factory_1/boot_result.json').is_file():raise RuntimeError('factory_1 not complete')
 failure=None
 try:
  child('factory2',['boot_run.py','factory','2'],5400)
  upper_before()
  child('apply_programs',['write_state.py','programs'],3600)
  child('programs_undone1',['boot_run.py','programs_undone','1'],5400)
  child('programs_undone2',['boot_run.py','programs_undone','2'],5400)
  child('apply_libraries',['write_state.py','libraries'],10800)
  child('all_undone1',['boot_run.py','all_undone','1'],5400)
  child('all_undone2',['boot_run.py','all_undone','2'],5400)
 except BaseException as e:
  failure=e;p.log('EXPERIMENT_STOP '+repr(e))
 finally:
  try:child('restore',['write_state.py','restore'],10800)
  except BaseException as e:
   p.log('RESTORE_FAILED '+repr(e));failure=failure or e
  else:
   try:child('final_recovery',['final_recovery.py'],1800)
   except BaseException as e:
    p.log('FINAL_RECOVERY_FAILED '+repr(e));failure=failure or e
 if failure:raise failure

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
