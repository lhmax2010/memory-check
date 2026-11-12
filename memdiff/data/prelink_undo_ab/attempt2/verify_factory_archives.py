#!/usr/bin/env python3
"""Verify both factory memcheck gzip/tar attachments without loading in RAM."""
import gzip, hashlib, json, subprocess
from pathlib import Path
import preflight as p

HERE=p.HERE

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 rows=[];failures=[]
 for i in (1,2):
  tag=f'factory_{i}'
  p.log('VERIFY '+tag)
  root=HERE/'boots'/tag/'memcheck_pull'
  archives=list(root.rglob('05_elf/elf_files.tar.gz'))
  smaps=list(root.rglob('02_steady/smaps_raw.txt.gz'))
  if len(archives)!=1 or len(smaps)!=1:raise RuntimeError('attachments missing '+tag)
  for kind,path in [('elf_archive',archives[0]),('steady_smaps',smaps[0])]:
   result={'boot':tag,'kind':kind,'path':str(path.relative_to(HERE)),'bytes':path.stat().st_size,'sha256':sha(path)}
   try:
    with gzip.open(path,'rb') as f:
     while f.read(1024*1024):pass
    result['gzip_valid']=True
   except (EOFError,OSError) as e:
    result['gzip_valid']=False;result['gzip_error']=repr(e);failures.append(tag+' '+kind+' '+repr(e))
   if kind=='elf_archive':
    q=subprocess.run(['tar','-tzf',str(path)],stdin=subprocess.DEVNULL,capture_output=True,text=True,errors='replace',timeout=1200)
    result['tar_rc']=q.returncode;result['tar_entries']=len(q.stdout.splitlines());result['tar_stderr']=q.stderr
    if q.returncode:failures.append(tag+' tar '+q.stderr[-200:])
   rows.append(result)
   p.log('VALID '+tag+' '+kind+' bytes='+str(result['bytes']))
 (HERE/'factory_attachment_validation.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
 if failures:raise RuntimeError('; '.join(failures))

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
