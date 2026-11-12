#!/usr/bin/env python3
"""Resume A/B after a verified, no-write ETXTBSY stop timeout.

Factory_1 and factory_2 are preserved. The original-byte recovery check from
the prior attempt is a hard prerequisite. This script retains try/finally
restoration for any subsequent partial write.
"""
import json
from pathlib import Path
import preflight as p
from orchestrate import child

HERE=p.HERE

def main():
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 for i in (1,2):
  if not (HERE/f'boots/factory_{i}/boot_result.json').is_file():raise RuntimeError('factory baseline incomplete')
 for prior in (HERE/'recovery_failed1/recovery_result.json',HERE/'recovery_failed2/recovery_result.json'):
  if not prior.is_file():raise RuntimeError('prior recovery evidence missing '+str(prior))
  r=json.loads(prior.read_text())
  if r['status']!='DONE' or not r['stage_cleaned'] or not r['prelink_diag']['has_ok']:
   raise RuntimeError('prior recovery did not fully pass '+str(prior))
 if not (HERE/'stage_complete.json').is_file():raise RuntimeError('restaging missing')
 failure=None
 try:
  child('apply_programs_retry',['write_state.py','programs'],3600)
  child('programs_undone1',['boot_run.py','programs_undone','1'],5400)
  child('programs_undone2',['boot_run.py','programs_undone','2'],5400)
  child('apply_libraries',['write_state.py','libraries'],10800)
  child('all_undone1',['boot_run.py','all_undone','1'],5400)
  child('all_undone2',['boot_run.py','all_undone','2'],5400)
 except BaseException as e:
  failure=e;p.log('RETRY_STOP '+repr(e))
 finally:
  try:child('restore_retry',['write_state.py','restore'],10800)
  except BaseException as e:p.log('RETRY_RESTORE_FAILED '+repr(e));failure=failure or e
  else:
   try:child('final_recovery_retry',['final_recovery.py'],1800)
   except BaseException as e:p.log('RETRY_RECOVERY_FAILED '+repr(e));failure=failure or e
 if failure:raise failure

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
