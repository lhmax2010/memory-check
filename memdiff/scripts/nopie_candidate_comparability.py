#!/usr/bin/env python3
"""Bounded offline audit of four noPIE memory candidates; never runs target ELF."""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,re,subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
READELF=Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf')
BASES={
 'GCC':ROOT/'memdiff/data/gcc_baseline/elf/files',
 'LLVM3':ROOT/'memdiff/data/llvm_round3/elf/files',
 'noPIE':ROOT/'memdiff/data/noPIE_prelink_validation/boots/boot1/collection/elf',
}
PATHS=('/usr/lib/libpisa-ipc.so','/usr/lib/libvorbisenc.so.2.0.12',
       '/usr/lib/libsndfile.so.1.0.37','/usr/bin/avocd',
       '/usr/apps/com.samsung.tizen.argot/bin/argot',
       '/opt/usr/share/argot/.local/bin/tsr',
       '/opt/usr/share/argot/.local/bin/tsr-bwrap')
MAIN_C=('/usr/lib/libpisa-ipc.so','/usr/lib/libvorbisenc.so.2.0.12','/usr/bin/avocd')
METRICS=('Pss','SwapPss','Private_Dirty','Rss','Shared_Clean')
SECT=re.compile(r'^\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+')
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
 return h.hexdigest()
def read(path):
 with path.open(newline='') as f:yield from csv.DictReader(f,delimiter='\t')
def put(path,rows):
 if not rows:return
 fields=list(dict.fromkeys(k for x in rows for k in x))
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader()
  for x in rows:w.writerow({k:x.get(k,'NA') for k in fields})
def now():return datetime.now().astimezone().isoformat()
def run_command(args,log):
 p=subprocess.run(args,capture_output=True,text=True,errors='replace',stdin=subprocess.DEVNULL)
 log.append({'command':' '.join(args[:-1])+' <ELF:'+args[-1].split('/elf/')[-1]+'>',
             'return_code':p.returncode,'stderr':p.stderr.strip()[:1000] or '-'})
 if p.returncode:raise RuntimeError(f'readelf rc={p.returncode}: {args[-1]}: {p.stderr}')
 return p.stdout

def inventory_versions():
 gcc={}
 with (ROOT/'memdiff/data/gcc_baseline/survey/predeployment/rpm.tsv').open(newline='') as stream:
  for row in csv.reader(stream,delimiter='\t'):
   if len(row)>=3:gcc[row[0]]=row[1]+'.'+row[2]
 llvm={}
 for line in (ROOT/'memdiff/data/llvm_round3/survey/packages/rpm_qa_sorted.txt').read_text().splitlines():
  for package in ('libpisa-ipc','libvorbisenc','libsndfile','avoc-daemon','argot','com.samsung.tizen.tsr'):
   if line.startswith(package+'-'):llvm[package]=line[len(package)+1:]
 return gcc,llvm

def scan_all_mappers(manifest,progress):
 out=[]
 for e in manifest['snapshots']:
  boot=e['label'];seen=defaultdict(set);origins=defaultdict(set)
  if e['kind']=='historical_smaps':
   pid=None
   with gzip.open(ROOT/e['smaps'],'rt',errors='replace') as stream:
    for line in stream:
     if line.startswith('### '):
      fields=line.split();pid=fields[1] if len(fields)>1 else None
     elif pid is not None and ('libsndfile.so' in line or 'libvorbisenc.so' in line):
      fields=line.split(None,5)
      if len(fields)>5 and re.match(r'^[0-9a-f]+-[0-9a-f]+$',fields[0]):
       p=fields[5].strip();name='sndfile' if 'libsndfile.so' in p else 'vorbisenc'
       seen[name].add(pid);origins[name].add(p)
  else:
   p=(ROOT/e['collection']).parent.parent/'budget/vmas_all.tsv'
   for r in read(p):
    path=r['path']
    if 'libsndfile.so' in path or 'libvorbisenc.so' in path:
     name='sndfile' if 'libsndfile.so' in path else 'vorbisenc'
     seen[name].add(r['pid']);origins[name].add(path)
  out.append({'boot':boot,'all_measured_sndfile_mappers':len(seen['sndfile']),
              'all_measured_vorbisenc_mappers':len(seen['vorbisenc']),
              'vorbisenc_without_sndfile':len(seen['vorbisenc']-seen['sndfile']),
              'mapped_vorbisenc_paths':'; '.join(sorted(origins['vorbisenc'])) or 'not_observed',
              'source':e['smaps'] if e['kind']=='historical_smaps' else str(p.relative_to(ROOT))})
  progress.write(f'{now()} all-mappers {boot} {len(seen["vorbisenc"])} vorbisenc\n');progress.flush()
 return out

def collect_C(prior):
 agg=defaultdict(lambda:{k:0 for k in METRICS})
 with gzip.open(prior/'classified_vmas.tsv.gz','rt') as stream:
  for r in csv.DictReader(stream,delimiter='\t'):
   if r['path'] not in MAIN_C and not r['path'].startswith('/usr/lib/libsndfile.so'):continue
   key=(r['boot'],r['identity_key'],r['path'],r['category'])
   for k in METRICS:
    if r[k]=='NA':raise ValueError(f'missing {k}: {key}')
    agg[key][k]+=int(r[k])
 out=[]
 for (boot,identity,path,cat),v in sorted(agg.items()):
  out.append({'boot':boot,'identity':identity,'path':path,'category':cat,**v,
              'Pss_plus_SwapPss_kB':v['Pss']+v['SwapPss']})
 return out

def elf_evidence(commands,progress,collection):
 gcc,llvm=inventory_versions();result=[];symbols=[]
 oldpull={image:{r['path']:r for r in json.loads((ROOT/f'memdiff/data/{"gcc_baseline" if image=="GCC" else "llvm_round3"}/elf/pull_records.json').read_text())}
          for image in ('GCC','LLVM3')}
 newpull={r['path']:r for r in json.loads(collection.read_text())['pulled'] if isinstance(r,dict) and 'path' in r}
 package={'/usr/lib/libpisa-ipc.so':'libpisa-ipc',
          '/usr/lib/libvorbisenc.so.2.0.12':'libvorbisenc',
          '/usr/lib/libsndfile.so.1.0.37':'libsndfile',
          '/usr/bin/avocd':'avoc-daemon',
          '/usr/apps/com.samsung.tizen.argot/bin/argot':'argot',
          '/opt/usr/share/argot/.local/bin/tsr':'com.samsung.tizen.tsr',
          '/opt/usr/share/argot/.local/bin/tsr-bwrap':'com.samsung.tizen.tsr'}
 for path in PATHS:
  for image,root in BASES.items():
   source=root/path.lstrip('/')
   r={'path':path,'image':image,'source':str(source.relative_to(ROOT)),
      'package':package[path],'available':int(source.is_file()),'package_version_release':'not_saved'}
   if image=='GCC' and package[path] in gcc:r['package_version_release']=gcc[package[path]]
   if image=='LLVM3' and package[path] in llvm:r['package_version_release']=llvm[package[path]]
   if image=='noPIE' and path=='/usr/bin/avocd':r['package_version_release']='0.1.0-1.armv7l (saved rpm -qf)'
   if not source.is_file():result.append(r);continue
   r['sha256']=sha(source)
   prev=oldpull.get(image,{}).get(path) if image!='noPIE' else newpull.get(path)
   r['pull_record_match']=int(bool(prev) and r['sha256']==(prev.get('sha256') if image!='noPIE' else prev.get('board_sha256')))
   sw=run_command([str(READELF),'-SW',str(source)],commands)
   dyn=run_command([str(READELF),'-dW',str(source)],commands)
   hdr=run_command([str(READELF),'-hW','-lW','-nW',str(source)],commands)
   secs={m[1]:(int(m[2],16),int(m[3],16)) for line in sw.splitlines() if (m:=SECT.match(line))}
   r['build_id']=(re.search(r'Build ID:\s+([0-9a-fA-F]+)',hdr) or [None,'not_found'])[1]
   r['elf_type']=(re.search(r'^\s*Type:\s+(\S+)',hdr,re.M) or [None,'not_found'])[1]
   r['needed']=';'.join(re.findall(r'\(NEEDED\).*?\[([^]]+)\]',dyn))
   r['prelink_undo']=int('.gnu.prelink_undo' in secs);r['gnu_liblist']=int('.gnu.liblist' in secs)
   r['gnu_prelinked_dynamic']=int('GNU_PRELINKED' in dyn)
   r['PT_LOAD']='; '.join(' '.join(line.split()) for line in hdr.splitlines() if line.lstrip().startswith('LOAD '))
   blob=source.read_bytes()
   for sec in ('.text','.rodata','.dynsym','.dynstr','.rel.dyn','.rel.plt','.gnu.conflict'):
    if sec in secs:
     off,size=secs[sec];r[sec+'_bytes']=size;r[sec+'_sha256']=hashlib.sha256(blob[off:off+size]).hexdigest()
    else:r[sec+'_bytes']='absent';r[sec+'_sha256']='absent'
   if '.comment' in secs:
    comment=run_command([str(READELF),'-p','.comment',str(source)],commands)
    r['comment']='; '.join(line.strip() for line in comment.splitlines() if re.search(r'\[\s*[0-9a-fA-F]+\]',line))
   else:r['comment']='section_absent'
   if path.endswith('libsndfile.so.1.0.37') or path.endswith('libvorbisenc.so.2.0.12'):
    sym=run_command([str(READELF),'-Ws',str(source)],commands)
    names=set()
    for line in sym.splitlines():
     if re.search(r'\bUND\b',line):
      name=line.split()[-1] if line.split() else ''
      if path.endswith('libsndfile.so.1.0.37') and name.startswith('vorbis_'):names.add(name)
     elif path.endswith('libvorbisenc.so.2.0.12') and re.search(r'\b(?:GLOBAL|WEAK)\b',line):
      name=line.split()[-1] if line.split() else ''
      if name.startswith('vorbis_'):names.add(name)
    if path.endswith('libsndfile.so.1.0.37'):r['undefined_vorbis_symbols']=len(names)
    else:r['defined_vorbisenc_symbols']=len(names)
    symbols.extend({'image':image,'owner_path':path,'symbol':s,'symbol_kind':'undefined' if 'libsndfile' in path else 'defined'} for s in sorted(names))
   result.append(r)
   progress.write(f'{now()} ELF {image} {path}\n');progress.flush()
 return result,symbols

def main_run(prior,manifest_path,out):
 out.mkdir(parents=True,exist_ok=True)
 manifest=json.loads(manifest_path.read_text())
 inputs=[prior/'classified_vmas.tsv.gz',prior/'C_processes_six.tsv',prior/'C_file_comparisons.tsv',
         prior/'static_elf_evidence.tsv',prior/'argot_capture_audit.tsv',manifest_path,
         ROOT/'memdiff/data/gcc_baseline/survey/predeployment/rpm.tsv',
         ROOT/'memdiff/data/llvm_round3/survey/packages/rpm_qa_sorted.txt',
         ROOT/'memdiff/data/noPIE_followup_validation/T-KSU2EJAKUC-0101-PERF-202611120549/20261113_followup/target_rpms.txt']
 inputrows=[{'source':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in inputs]
 put(out/'input_refs.tsv',inputrows)
 commands=[]
 with (out/'progress.log').open('w') as progress:
  progress.write(f'{now()} begin\n');progress.flush()
  c=collect_C(prior);put(out/'focus_C_mappings.tsv',c)
  progress.write(f'{now()} classified focused C mappings {len(c)}\n');progress.flush()
  allmap=scan_all_mappers(manifest,progress);put(out/'all_measured_mappers.tsv',allmap)
  collection=(ROOT/manifest['snapshots'][4]['collection'])
  elf,syms=elf_evidence(commands,progress,collection);put(out/'focus_elf.tsv',elf);put(out/'libsndfile_undefined_vorbis.tsv',syms)
  progress.write(f'{now()} complete\n')
 put(out/'readelf_commands.tsv',commands)
 # Input and pulled-ELF consistency are hard gates, not broad statistical tests.
 failures=[r for r in elf if r['available']==1 and r['pull_record_match']!=1]
 if failures:raise ValueError(f'ELF pull hashes differ: {[(r["image"],r["path"]) for r in failures]}')
 focus={b:sum(r['Pss_plus_SwapPss_kB'] for r in c if r['boot']==b and r['path']=='/usr/lib/libpisa-ipc.so') for b in ('GCC1','GCC2','LLVM31','LLVM32','noPIE1','noPIE2')}
 if focus!={'GCC1':1003,'GCC2':1001,'LLVM31':1472,'LLVM32':1472,'noPIE1':1460,'noPIE2':1460}:
  raise ValueError(f'pisa prior-table mismatch: {focus}')
 vorbis={b:sum(r['Pss_plus_SwapPss_kB'] for r in c if r['boot']==b and r['path']=='/usr/lib/libvorbisenc.so.2.0.12') for b in focus}
 if vorbis!={'GCC1':0,'GCC2':0,'LLVM31':1005,'LLVM32':1005,'noPIE1':819,'noPIE2':819}:
  raise ValueError(f'vorbis prior-table mismatch: {vorbis}')
 for r in allmap:
  if r['vorbisenc_without_sndfile']!=0:raise ValueError(f'vorbis mapper not loading sndfile: {r["boot"]}')
 for image in ('LLVM3','noPIE'):
  undefined={r['symbol'] for r in syms if r['image']==image and r['symbol_kind']=='undefined'}
  defined={r['symbol'] for r in syms if r['image']==image and r['symbol_kind']=='defined'}
  if undefined & defined:raise ValueError(f'libsndfile directly imports encoder symbol in {image}: {undefined & defined}')
 (out/'validation.json').write_text(json.dumps({'status':'PASS','libpisa_C_totals_kB':focus,
  'libvorbisenc_C_totals_kB':vorbis,
  'ELF_pull_hash_matches':sum(r['available']==1 for r in elf),'readelf_commands':len(commands),
  'all_measured_vorbisenc_mappers':{r['boot']:r['all_measured_vorbisenc_mappers'] for r in allmap}},indent=2)+'\n')
 print(now(),'PASS',len(c),'focused C rows',len(elf),'ELF identity rows',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--prior',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();state='成功'
 try:main_run(a.prior.resolve(),a.manifest.resolve(),a.out.resolve())
 except Exception:state='失败';raise
 finally:print('已结束',now(),'状态='+state,flush=True)
