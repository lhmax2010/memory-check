#!/usr/bin/env python3
"""Pull current board prelink candidates, cross-readelf them, and record SHA pairs."""
import csv, hashlib, json, os, re, shlex, subprocess, sys
from pathlib import Path
import preflight as p
import inventory as inv

HERE=p.HERE
ROOT=HERE/'pulled_root'
ELFOUT=HERE/'readelf'
OLD=HERE.parents[3]/'gcc_baseline'/'elf'/'files'

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def board_quiet(path):
 cmd='sha256sum '+shlex.quote(path)
 wrapped=cmd+"; __ab_rc=$?; printf '\\n__AB_RC__%d\\n' \"$__ab_rc\""
 proc=subprocess.run([p.SDB,'-s',p.IP,'shell',wrapped],stdin=subprocess.DEVNULL,capture_output=True,timeout=60)
 out=proc.stdout.decode(errors='replace')
 m=re.search(r'\n__AB_RC__(\d+)\s*$',out)
 rc=proc.returncode or (int(m.group(1)) if m else 255)
 sm=re.search(r'\b[0-9a-f]{64}\b',out)
 return rc,sm.group() if sm else '',proc.stderr.decode(errors='replace')

def main():
 if not p.IP:raise RuntimeError('PRELINK_BOARD_IP required')
 if not json.loads((HERE/'native_scan_summary.json').read_text())['remote_rc']==0:raise RuntimeError('native scan did not pass')
 libs=set((HERE/'undo_marker_candidates.txt').read_text().splitlines())|set((HERE/'native_gnu_prelinked_paths.txt').read_text().splitlines())
 paths=sorted(x for x in libs if x)+list(inv.TARGETS)
 paths=list(dict.fromkeys(paths))
 ROOT.mkdir(exist_ok=True);ELFOUT.mkdir(exist_ok=True)
 old_root=Path('memdiff/data/gcc_baseline/elf/files')
 root=False
 try:
  rc,_,_=p.run('pull_root_on',[p.SDB,'-s',p.IP,'root','on'])
  if rc:raise RuntimeError('root on failed')
  root=True
  rc,uid,_=p.board('pull_uid','id -u')
  if rc or uid.strip()!='0':raise RuntimeError('root UID missing')
  with (HERE/'pull_classify.tsv').open('w',newline='') as f:
   writer=csv.writer(f,delimiter='\t')
   writer.writerow(['path','category','pull_rc','board_sha_rc','board_sha256','host_sha256','bytes','readelf_h_rc','readelf_s_rc','readelf_d_rc','elf_type','gnu_liblist','gnu_prelinked','prelink_undo','old_sha256','matches_old','selected','exclusion_reason','stderr'])
   for i,path in enumerate(paths,1):
    local=ROOT/path.lstrip('/')
    local.parent.mkdir(parents=True,exist_ok=True)
    proc=subprocess.run([p.SDB,'-s',p.IP,'pull',path,str(local)],stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
    pull_rc=proc.returncode
    board_rc,board_sha,board_err=board_quiet(path)
    host_sha=sha(local) if pull_rc==0 and local.is_file() else ''
    size=local.stat().st_size if host_sha else 0
    outputs={};rcs={}
    if host_sha:
     base=ELFOUT/(hashlib.sha256(path.encode()).hexdigest()[:16])
     for name,opt in [('h','-hW'),('s','-SW'),('d','-dW')]:
      q=subprocess.run([p.READELF,opt,str(local)],stdin=subprocess.DEVNULL,capture_output=True,timeout=60)
      rcs[name]=q.returncode
      (Path(str(base)+'.'+name+'.stdout')).write_bytes(q.stdout)
      (Path(str(base)+'.'+name+'.stderr')).write_bytes(q.stderr)
      outputs[name]=q.stdout.decode(errors='replace')
    typ=re.search(r'Type:\s+(\S+)',outputs.get('h',''))
    typ=typ.group(1) if typ else ''
    liblist='(GNU_LIBLIST)' in outputs.get('d','')
    prelinked='(GNU_PRELINKED)' in outputs.get('d','')
    undo='.gnu.prelink_undo' in outputs.get('s','')
    category='library' if path in libs else 'program'
    reason=''
    if path in ('/usr/lib/ld-linux.so.3','/usr/apps/boot-helper-dyboost-tv/bin/boot-helper-dyboost-tv'):
     reason='fixed_exclusion'
    elif category=='program' and not (liblist and undo):reason='not_both_program_markers'
    elif category=='library' and not (prelinked or undo):reason='not_library_marker'
    if pull_rc or board_rc or not host_sha or host_sha!=board_sha or any(rcs.get(x,1) for x in ('h','s','d')):
     reason=reason or 'pull_sha_or_readelf_failure'
    old=old_root/path.lstrip('/')
    oldsha=sha(old) if old.is_file() else ''
    writer.writerow([path,category,pull_rc,board_rc,board_sha,host_sha,size,rcs.get('h',''),rcs.get('s',''),rcs.get('d',''),typ,int(liblist),int(prelinked),int(undo),oldsha,int(bool(oldsha and oldsha==host_sha)),int(not reason),reason,(proc.stderr.decode(errors='replace')+' '+board_err).replace('\t',' ').replace('\n',' ')[:300]])
    f.flush()
    if i%25==0 or i==len(paths):p.log(f'PULL_CLASSIFY {i}/{len(paths)}')
  p.log('pull classify done')
 finally:
  if root:
   p.run('pull_root_off',[p.SDB,'-s',p.IP,'root','off'])
   rc,uid,_=p.board('pull_sdk_uid','id -u')
   if rc or uid.strip()=='0':raise RuntimeError('sdb root off failed')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
