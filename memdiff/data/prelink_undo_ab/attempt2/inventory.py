#!/usr/bin/env python3
"""Read-only inventory of prelink.conf directories and 19 target paths."""
import json, os, sys
from pathlib import Path
import preflight as p

HERE=p.HERE
DIRS=['/opt/usr/apps/com.samsung.tv.slive-daemon/lib','/lib','/usr/lib','/prd/usr/lib','/usr/lib/was-api','/usr/lib/ecore_imf/modules/isf/v-1.13','/usr/lib/gstreamer-1.0','/usr/lib/pulseaudio']
TARGETS=['/usr/bin/tvs-daemon','/usr/bin/TIFSDaemon','/usr/bin/app-boot-manager','/usr/apps/boot-helper-dyboost-tv/bin/boot-helper-dyboost-tv','/usr/bin/fastinit','/usr/bin/avocd','/usr/bin/fastlogo','/usr/bin/amd','/usr/bin/fastvideo','/usr/apps/org.tizen.tv-viewer/bin/tv-viewer','/usr/bin/rscmgr-service','/usr/bin/pulseaudio','/usr/apps/org.tizen.btapp/bin/btapp','/usr/bin/hdmicec-service','/usr/apps/org.tizen.acm-service/bin/acm-service','/usr/bin/launchpad-loader','/usr/bin/launchpad-process-pool','/usr/bin/app_launcher','/usr/apps/org.tizen.welcome-mode/bin/welcome-mode']

def main():
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 if not (HERE/'tvs_gate.json').is_file():raise RuntimeError('preflight gate missing')
 gate=json.loads((HERE/'tvs_gate.json').read_text())
 if not all(gate['markers'].values()):raise RuntimeError('tvs marker gate failed')
 root=False
 try:
  rc,_,_=p.run('inventory_root_on',[p.SDB,'-s',p.IP,'root','on'])
  if rc:raise RuntimeError('root on failed')
  root=True
  rc,uid,_=p.board('inventory_uid','id -u')
  if rc or uid.strip()!='0':raise RuntimeError('root UID missing')
  dirs=' '.join(DIRS)
  cmd=f'for d in {dirs}; do if [ -d "$d" ]; then find "$d" -xdev -type f -printf "%p\\t%s\\n"; fi; done'
  rc,files,_=p.board('all_regular_files',cmd,180)
  if rc:raise RuntimeError('find failed')
  lines=sorted(set(x.strip() for x in files.splitlines() if x.strip()))
  (HERE/'all_regular_files.tsv').write_text('path\tbytes\n'+'\n'.join(lines)+'\n')
  p.log(f'all regular files: {len(lines)}')
  cmd=f'for d in {dirs}; do if [ -d "$d" ]; then find "$d" -xdev -type f -exec grep -alF .gnu.prelink_undo {{}} +; fi; done'
  rc,candidates,_=p.board('undo_marker_candidates',cmd,180)
  if rc:raise RuntimeError('candidate grep failed')
  paths=sorted(set(x.strip() for x in candidates.splitlines() if x.strip()))
  (HERE/'undo_marker_candidates.txt').write_text('\n'.join(paths)+'\n')
  p.log(f'undo marker candidates: {len(paths)}')
  cmd='for f in '+' '.join(TARGETS)+'; do if [ -f "$f" ]; then printf "present\\t%s\\n" "$f"; else printf "missing\\t%s\\n" "$f"; fi; done'
  rc,targets,_=p.board('targets_present',cmd)
  if rc:raise RuntimeError('target existence failed')
  (HERE/'targets_present.tsv').write_text('state\tpath\n'+targets)
 finally:
  if root:
   p.run('inventory_root_off',[p.SDB,'-s',p.IP,'root','off'])
   rc,uid,_=p.board('inventory_sdk_uid','id -u')
   if rc or uid.strip()=='0':raise RuntimeError('sdb root off verification failed')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
