#!/usr/bin/env python3
"""Bounded, read-only board snapshot with explicit remote exit status."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

CMDS={
 'identity':'id -u; uname -m; tr -d "\\000" </proc/device-tree/model; cat /proc/cmdline; cat /etc/os-release; cat /proc/version; cat /proc/sys/kernel/random/boot_id; uptime; date -Iseconds',
 'failed_units':'systemctl --failed --no-pager --plain',
 'service_health':'for u in com.samsung.tv.qse-daemon.service kzram.service org.tizen.mbr-daemon.service security-emdaemon.service ses-usb-installer@sda1.service vdca-update.service org.tizen.acm-service.service; do echo "===== $u"; systemctl show "$u" -p ActiveState,SubState,Result,ExecMainStatus,NRestarts,ActiveEnterTimestamp --no-pager; done',
 'processes':'ps -eo pid,ppid,lstart,comm,args',
 'crash_files':'for d in /opt/usr/share/crash /opt/share/crash/dump /opt/share/crash; do if test -d "$d"; then echo "===== $d"; find "$d" -maxdepth 3 -type f -printf "%p\\t%s\\t%TY-%Tm-%TdT%TH:%TM:%TS%TZ\\n"; fi; done',
 'dmesg_signals':'dmesg | grep -Ei "(signal (6|11|4)|SIGABRT|SIGSEGV|SIGILL|out of memory|oom-kill|NOT signed|kUEP|signature)"',
 'journal_anomaly':'journalctl -b --no-pager -n 600 2>&1 | grep -Ei "(acm-service|TIFSDaemon|failed|crash|restart|signal|oom)"',
 'packages':'rpm -qa | sort | grep -Ei "(^glibc|^clang|^llvm|^prelink|^tizen|^vdprelink|^tvs|^fkp|^ffmpeg|^gstreamer)"',
 'media':'find /opt/usr /opt/share /usr/share -type f \\( -iname "*.h265" -o -iname "*.hevc" -o -iname "*h265*.mp4" \\) 2>/dev/null | head -80; command -v ffmpeg; command -v gst-launch-1.0; gst-inspect-1.0 avdec_h265 2>&1 | tail -30',
 'tifs':'rpm -qf /usr/bin/TIFSDaemon; ls -l /opt/usr/apps/Ddrm/fkp/lib/libfkpInternal.so /hal/lib/libcamera-control.so /usr/lib/libfkp.so.0.1.0 2>&1; grep -E "libfkpInternal|libcamera-control" /proc/$(pidof TIFSDaemon | awk "{print \\$1}")/maps 2>&1',
}

def remote(ip,cmd,timeout=120):
    marker='__FOLLOWUP_REMOTE_RC__='
    wrapper='sh -c '+shlex.quote(cmd+'; __followup_rc=$?; printf "\\n'+marker+'%s\\n" "$__followup_rc"')
    try:p=subprocess.run(['sdb','-s',ip,'shell',wrapper],capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired as e:return {'transport':'timeout','remote_rc':None,'stdout':str(e.stdout),'stderr':str(e.stderr)}
    m=re.search(marker+r'(\d+)',p.stdout)
    return {'transport':'ok' if p.returncode==0 and m else 'failed','sdb_rc':p.returncode,'remote_rc':int(m.group(1)) if m else None,'stdout':p.stdout,'stderr':p.stderr}

def main():
    a=argparse.ArgumentParser();a.add_argument('--ip',default='192.168.108.26');a.add_argument('--out',type=Path,required=True);a.add_argument('--label',choices=['T0','T1'],required=True);x=a.parse_args();x.out.mkdir(parents=True,exist_ok=True)
    log=[]
    try:
      for name,cmd in CMDS.items():
        print(datetime.now().astimezone().isoformat(),x.label,name,flush=True)
        r=remote(x.ip,cmd)
        (x.out/f'{x.label}_{name}.txt').write_text(r['stdout']+'\nSTDERR:\n'+r['stderr'])
        log.append({'name':name,'command':cmd,'transport':r['transport'],'sdb_rc':r.get('sdb_rc'),'remote_rc':r['remote_rc'],'file':f'{x.label}_{name}.txt'})
        if name=='identity' and not all(z in r['stdout'] for z in ('armv7l','NT72671D','KSU2E','T-KSU2EJAKUC-0101-PERF-202611120549')):
          raise RuntimeError('identity gate failed')
      (x.out/f'{x.label}_commands.json').write_text(json.dumps(log,indent=2))
      print('已结束',datetime.now().astimezone().isoformat(),'状态=成功',flush=True)
    except Exception as e:
      (x.out/f'{x.label}_commands.json').write_text(json.dumps(log,indent=2))
      print('已结束',datetime.now().astimezone().isoformat(),'状态=失败',repr(e),file=sys.stderr,flush=True);raise
if __name__=='__main__':main()
