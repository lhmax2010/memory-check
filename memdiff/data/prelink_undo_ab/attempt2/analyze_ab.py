#!/usr/bin/env python3
"""Analyze six GCC A/B smaps snapshots at identical 02_steady points."""
import csv, gzip, json, re, subprocess
from collections import Counter, defaultdict
from pathlib import Path
import preflight as p

HERE=p.HERE
M=HERE.parents[2]
STATES=('factory','programs_undone','all_undone')
TAGS=[f'{state}_{index}' for state in STATES for index in (1,2)]
PROCESS=re.compile(r'^###\s+(\d+)\s+([^ ]+)\s+(.*)$')
MAPPING=re.compile(r'^[0-9a-f]+-[0-9a-f]+\s+([rwxps-]{4})\s+[0-9a-f]+\s+\S+\s+\d+\s*(.*?)\s*$')
METRIC=re.compile(r'^(Pss|SwapPss|Private_Dirty):\s+(\d+)\s+kB$')
SEC=re.compile(r'^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+[0-9a-fA-F]+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s')
LOADER=lambda n:n in ('.dynsym','.dynstr','.gnu.hash','.hash','.rel.dyn','.rel.plt') or n.startswith('.gnu.version')

def tsv(path,rows,fields=None):
 rows=list(rows)
 fields=fields or (list(rows[0]) if rows else [])
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,delimiter='\t',fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)

def snapshot(tag):
 source=HERE/'boots'/tag/'memcheck_pull'
 dirs=list(source.rglob('02_steady'))
 if len(dirs)!=1:raise RuntimeError(f'{tag}: expected one 02_steady, got {dirs}')
 return dirs[0]

def parse_smaps(source,wanted_libs,nonpie,ten):
 process={};lib_rows=Counter();mapper=defaultdict(set)
 pid=None;exe='';path='';seg='';metric={}
 def flush():
  if pid is None or path not in wanted_libs:return
  key=(pid,exe,path,seg)
  if seg in ('r--','rw-'):
   lib_rows[key,'Private_Dirty']+=metric.get('Private_Dirty',0)
  if seg=='r-x':
   lib_rows[key,'Pss']+=metric.get('Pss',0)
   mapper[path].add(exe)
 with gzip.open(source,'rt',errors='replace') as f:
  for line in f:
   line=line.rstrip('\n')
   proc=PROCESS.match(line)
   if proc:
    flush();pid=int(proc[1]);exe=proc[3].strip();process[pid]={'comm':proc[2],'exe':exe}
    path='';seg='';metric={};continue
   vm=MAPPING.match(line)
   if vm:
    flush();seg=vm[1][:3];path=vm[2].removesuffix(' (deleted)');metric={};continue
   met=METRIC.match(line)
   if met:metric[met[1]]=int(met[2])
 flush()
 return process,lib_rows,mapper

def rollup(path,process,nonpie,ps_path):
 total=0;group=0;rows=[];missing=[]
 ps_lines={}
 for line in ps_path.read_text(errors='replace').splitlines():
  m=re.match(r'^\s*(\d+)\s',line)
  if m:ps_lines[int(m[1])]=line
 for line in path.read_text().splitlines():
  f=line.split()
  if len(f)<10 or not f[8].isdigit():continue
  pid=int(f[8]);v=int(f[0]);total+=v
  if pid in process:
   exe=process[pid]['exe'];comm=process[pid]['comm'];smaps_present=1
  else:
   candidates=[x for x in nonpie if x in ps_lines.get(pid,'')]
   exe=candidates[0] if len(candidates)==1 else ''
   comm=f[9];smaps_present=0
   missing.append(f'{pid}:{comm}:{exe or "exe_unresolved"}')
  is15=exe in nonpie
  if is15:group+=v
  rows.append({'pid':pid,'comm':comm,'exe':exe,'Pss_plus_SwapPss_kB':v,'Pss_kB':int(f[1]),'SwapPss_kB':int(f[6]),'GCC_nonPIE_15':int(is15),'smaps_present':smaps_present})
 return total,group,rows,missing

def meminfo(path):
 out={}
 for line in path.read_text().splitlines():
  m=re.match(r'^(PageTables|MemAvailable):\s+(\d+)\s+kB',line)
  if m:out[m[1]]=int(m[2])
 if set(out)!={'PageTables','MemAvailable'}:raise RuntimeError('meminfo fields missing '+str(path))
 return out

def section_sizes(path):
 elf_root=next((x for x in path.parents if x.name=='elf'),None)
 if elf_root is None:raise RuntimeError('ELF root missing for '+str(path))
 readelf_dir=elf_root.parent/'readelf';readelf_dir.mkdir(exist_ok=True)
 label=str(path.relative_to(elf_root)).replace('/','__')
 q=subprocess.run([p.READELF,'-SW',str(path)],stdin=subprocess.DEVNULL,capture_output=True,text=True,errors='replace',timeout=120)
 (readelf_dir/(label+'.SW.txt')).write_text(f'rc={q.returncode}\n{q.stdout}\nSTDERR:\n{q.stderr}')
 if q.returncode:raise RuntimeError('readelf '+str(path)+' '+q.stderr)
 ph=subprocess.run([p.READELF,'-lW',str(path)],stdin=subprocess.DEVNULL,capture_output=True,text=True,errors='replace',timeout=120)
 (readelf_dir/(label+'.lW.txt')).write_text(f'rc={ph.returncode}\n{ph.stdout}\nSTDERR:\n{ph.stderr}')
 if ph.returncode:raise RuntimeError('readelf -lW '+str(path)+' '+ph.stderr)
 sections=[]
 for line in q.stdout.splitlines():
  m=SEC.match(line)
  if m and m[2]!='NOBITS':sections.append((m[1],int(m[3],16),int(m[4],16)))
 return sections

def pagemap13(tag):
 folder=HERE/'boots'/tag/'pagemap13'
 if not (folder/'collection.json').is_file():return []
 collection=json.loads((folder/'collection.json').read_text())
 if not collection.get('root_restored'):raise RuntimeError('pagemap root was not restored '+tag)
 page_size=collection['page_size']
 section_cache={};out=defaultdict(float);counts=Counter()
 for vm in collection['mappings']:
  if vm['perms'][:3]!='r-x':continue
  path=vm['path'];key=(vm['process'],path)
  if path not in section_cache:section_cache[path]=section_sizes(folder/'elf'/path.lstrip('/'))
  raw=(folder/vm['pagemap_file']).read_text()
  raw=re.sub(r'\s*__AB_RC__0\s*$','',raw)
  words=[int(x,16) for x in raw.split()]
  if len(words)!=vm['pages']:raise RuntimeError('pagemap word count '+tag+' '+path)
  for index,word in enumerate(words):
   if not word>>63&1:continue
   counts[key]+=page_size/1024
   start=vm['offset']+index*page_size;end=start+page_size
   for name,off,size in section_cache[path]:
    if not LOADER(name):continue
    overlap=max(0,min(end,off+size)-max(start,off))
    out[key]+=overlap/1024
 return [{'boot':tag,'process':k[0],'path':k[1],'rx_present_kB':counts[k],'loader_sections_resident_kB':round(out[k],6)} for k in sorted(counts)]

def main():
 classification=json.loads((M/'data/llvm_round3/analysis/classification.json').read_text())
 nonpie=set(classification['GCC_nonPIE'])
 selected=[x for x in csv.DictReader((HERE/'pull_classify.tsv').open(),delimiter='\t') if x['selected']=='1' and x['category']=='library']
 libraries={x['path'] for x in selected}
 ten={x['path'] for x in csv.DictReader((M/'data/prelink_group_attribution/gnu_liblist_executables.tsv').open(),delimiter='\t')}
 if len(libraries)!=417 or len(nonpie)!=15 or len(ten)!=10:raise RuntimeError(f'classification counts {len(libraries)} {len(nonpie)} {len(ten)}')
 perboot=[];proc_rows=[];lib_detailed=[];mappers={};snapshots={}
 for tag in TAGS:
  steady=snapshot(tag);snapshots[tag]=steady
  p.log('ANALYZE '+tag+' '+str(steady))
  process,raw,mapper=parse_smaps(steady/'smaps_raw.txt.gz',libraries,nonpie,ten)
  mappers[tag]=mapper
  total,group,rows,missing=rollup(steady/'proc_rollup.txt',process,nonpie,steady/'ps.txt')
  for x in rows:x['boot']=tag
  proc_rows+=rows
  dirty=Counter();rx=Counter()
  for (pid,exe,path,seg),metric in raw:
   val=raw[(pid,exe,path,seg),metric]
   if metric=='Private_Dirty':dirty['15' if exe in nonpie else 'other',seg]+=val
   if metric=='Pss':rx[path]+=val
   lib_detailed.append({'boot':tag,'pid':pid,'exe':exe,'path':path,'segment':seg,'metric':metric,'kB':val})
  mem=meminfo(steady/'meminfo.txt')
  entry={'boot':tag,'state':tag.rsplit('_',1)[0],'index':int(tag[-1]),'Pss_plus_SwapPss_kB':total,'GCC_nonPIE_15_Pss_plus_SwapPss_kB':group,'PageTables_kB':mem['PageTables'],'MemAvailable_kB':mem['MemAvailable'],'rollup_pids_missing_in_smaps':';'.join(missing)}
  for who in ('15','other'):
   for seg in ('r--','rw-'):entry[f'library_Private_Dirty_{who}_{seg}_kB']=dirty[who,seg]
  entry['_rx']=rx
  perboot.append(entry)
  p.log(f'ANALYZE_DONE {tag} userspace={total}kB mapped_libs={len(rx)}')
 # The prior report's group rule: a marked library is exclusive only when
 # both factory boots map it solely from the ten GNU_LIBLIST programs.
 class_by_path={}
 for path in libraries:
  exes=set().union(*(mappers[t].get(path,set()) for t in ('factory_1','factory_2')))
  class_by_path[path]='exclusive_ten' if exes and exes<=ten else 'also_other_or_absent'
 for entry in perboot:
  rx=entry.pop('_rx')
  for group in ('exclusive_ten','also_other_or_absent'):
   entry['library_rx_Pss_'+group+'_kB']=sum(v for path,v in rx.items() if class_by_path[path]==group)
 tsv(HERE/'per_boot_metrics.tsv',perboot)
 tsv(HERE/'process_rollup_rows.tsv',proc_rows)
 tsv(HERE/'library_mapping_metrics.tsv',lib_detailed)
 tsv(HERE/'library_rx_groups.tsv',[{'path':path,'group':class_by_path[path],**{t+'_mapper_exes':';'.join(sorted(mappers[t].get(path,set()))) for t in ('factory_1','factory_2')}} for path in sorted(libraries)])
 metrics=[k for k in perboot[0] if k.endswith('_kB')]
 deltas=[]
 for state in STATES[1:]:
  for metric in metrics:
   f=[float(x[metric]) for x in perboot if x['state']=='factory']
   s=[float(x[metric]) for x in perboot if x['state']==state]
   delta=sum(s)/2-sum(f)/2
   nr=max(abs(f[0]-f[1]),abs(s[0]-s[1]))
   deltas.append({'state':state,'metric':metric,'factory_boot1_kB':f[0],'factory_boot2_kB':f[1],'state_boot1_kB':s[0],'state_boot2_kB':s[1],'factory_mean_kB':sum(f)/2,'state_mean_kB':sum(s)/2,'delta_kB':delta,'factory_range_kB':abs(f[0]-f[1]),'state_range_kB':abs(s[0]-s[1]),'larger_than_both_ranges':int(abs(delta)>nr)})
 tsv(HERE/'state_deltas.tsv',deltas)
 page=[]
 for state in STATES:page+=pagemap13(state+'_1')
 tsv(HERE/'pagemap13_loader_residency.tsv',page,['boot','process','path','rx_present_kB','loader_sections_resident_kB'])
 (HERE/'analysis_sources.json').write_text(json.dumps({'boot_snapshots':{k:str(v) for k,v in snapshots.items()},'libraries':len(libraries),'nonpie_programs':sorted(nonpie),'ten_prelinked_programs':sorted(ten),'definitions':'Pss+SwapPss from proc_rollup; library Private_Dirty/Pss from smaps_raw; PageTables/MemAvailable from meminfo; 13-object pagemap only first boot per state'},ensure_ascii=False,indent=2)+'\n')
 p.log('ANALYSIS DONE')

if __name__=='__main__':
 status='成功'
 try:main()
 except BaseException as e:status='失败';p.log('ERROR '+repr(e));raise
 finally:print('已结束',p.now(),'状态='+status,flush=True)
