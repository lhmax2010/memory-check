#!/usr/bin/env python3
"""Offline LLVM-only PSS budget and static ELF ceilings from saved board evidence."""
import bisect
import collections
import csv
import datetime
import gzip
import json
import math
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
MEM = OUT.parents[1]
SRC = MEM / 'data/system_code_page_sections'
READELF = Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf')
FILT = READELF.with_name('armv7l-tizen-linux-gnueabi-c++filt')
LOG = OUT / 'progress.log'
MAP = re.compile(r'^([0-9a-f]+)-([0-9a-f]+)\s+([rwxps-]{4})\s+([0-9a-f]+)\s+(\S+)\s+(\d+)\s*(.*?)\s*$')
SEC = re.compile(r'^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+\S+\s+([A-Z]*)')
REL = re.compile(r'^\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+(R_ARM_[A-Z0-9_]+)\b')
SYM = re.compile(r'^\s*(\d+):\s+([0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+|\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)$')
LIB = re.compile(r'\.so(?:\.|$)')
LOADER_SECS = {'.dynsym','.dynstr','.gnu.hash','.hash','.rel.dyn','.rel.plt'}

def log(msg):
    line = f'{datetime.datetime.now().astimezone().isoformat()} {msg}'
    with LOG.open('a') as f: f.write(line+'\n')
    print(line, flush=True)

def rows(path):
    with path.open(newline='') as f: yield from csv.DictReader(f, delimiter='\t')

def write_tsv(name, data, fields=None):
    data=list(data)
    if fields is None: fields=list(data[0]) if data else ['value']
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n',extrasaction='ignore')
        w.writeheader();w.writerows(data)

def put_json(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def percentile(vals,p):
    if not vals:return 0
    x=sorted(vals);pos=(len(x)-1)*p;k=int(pos);d=pos-k
    return x[k]*(1-d)+x[min(k+1,len(x)-1)]*d

def smaps_budget():
    state=json.loads((SRC/'collection.json').read_text())
    valid={int(p['pid']) for p in state['processes'] if p['status']=='complete'}
    processes=[];vma_rows=[];mapper=collections.defaultdict(set);path_dirty=collections.Counter()
    budget=collections.Counter();negative=[]
    for n,pid in enumerate(sorted(valid),1):
        path=SRC/f'raw/process_{pid}.stdout'
        if not path.exists():continue
        active=False;rec=None;count=0;libs=set();pbudget=collections.Counter()
        def flush():
            nonlocal count
            if rec is None:return
            count+=1
            ps=int(rec.get('Pss',0));sw=int(rec.get('SwapPss',0));dirty=int(rec.get('Private_Dirty',0))
            pss_dirty=int(rec.get('Pss_Dirty',dirty))
            name=rec['path'];perms=rec['perms'];file=name.startswith('/')
            if file and LIB.search(name):libs.add(name)
            if file:mapper[name].add(pid)
            if file and perms.startswith('r-x'):cat='code_rx'
            elif file and perms.startswith('r--'):
                d=min(ps,dirty);sd=max(0,min(ps,pss_dirty)-d)
                pbudget['file_r--_private_dirty']+=d
                pbudget['file_r--_shared_dirty_Pss']+=sd
                pbudget['file_r--_clean']+=ps-d-sd
                if dirty>ps:negative.append((pid,name,perms,ps,dirty))
                cat=None
            elif file and perms.startswith('rw-'):
                d=min(ps,dirty);sd=max(0,min(ps,pss_dirty)-d)
                pbudget['file_rw-_private_dirty']+=d
                pbudget['file_rw-_shared_dirty_Pss']+=sd
                pbudget['file_rw-_clean']+=ps-d-sd
                if dirty>ps:negative.append((pid,name,perms,ps,dirty))
                cat=None
            elif file:cat='file_other'
            elif name=='[heap]':cat='anon_heap'
            elif name.startswith('[stack'):cat='anon_stack'
            elif not name or name.startswith('[anon:'):cat='anon_unlabelled'
            else:cat='anon_other_named'
            if cat:pbudget[cat]+=ps
            pbudget['SwapPss']+=sw;pbudget['Pss_total']+=ps
            if file:
                path_dirty[(pid,name)]+=dirty if perms.startswith(('r--','rw-')) else 0
            vma_rows.append({'pid':pid,'path':name,'perms':perms,'start':rec['start'],'end':rec['end'],
                             'offset':rec['offset'],'Pss_kB':ps,'Rss_kB':rec.get('Rss',0),
                             'Private_Dirty_kB':dirty,'Pss_Dirty_kB':pss_dirty,'SwapPss_kB':sw})
        with path.open(errors='replace') as f:
            for raw in f:
                line=raw.rstrip('\r\n')
                if line=='__SMAPS_BEGIN__':active=True;continue
                if line=='__SMAPS_END__':flush();rec=None;break
                if not active:continue
                m=MAP.match(line)
                if m:
                    flush();rec={'start':m[1],'end':m[2],'perms':m[3],'offset':m[4],
                                 'path':m[7].removesuffix(' (deleted)')};continue
                if rec is not None and ':' in line:
                    key,val=line.split(':',1)
                    if key in ('Pss','Pss_Dirty','SwapPss','Private_Dirty','Rss'):
                        z=re.search(r'\d+',val)
                        if z:rec[key]=int(z.group())
        budget.update(pbudget)
        processes.append({'pid':pid,'VMA_count':count,'mapped_library_count':len(libs),
                          'Pss_kB':pbudget['Pss_total'],'SwapPss_kB':pbudget['SwapPss']})
        if n%25==0:log(f'smaps {n}/{len(valid)}')
    write_tsv('process_distribution.tsv',processes)
    write_tsv('vmas_all.tsv',vma_rows)
    user_processes=[x for x in processes if x['VMA_count']>0]
    put_json('smaps_budget.json',{'budget_kB':dict(budget),'complete_processes':len(processes),
      'user_processes_with_smaps':len(user_processes),
      'collection_processes':len(state['processes']),'missing_or_exited':len(state['processes'])-len(processes),
      'negative_dirty_vs_pss_examples':negative[:20], 'negative_count':len(negative),
      'VMA_distribution':{k:percentile([x['VMA_count'] for x in user_processes],p) for k,p in [('median',.5),('p90',.9),('max',1)]},
      'library_distribution':{k:percentile([x['mapped_library_count'] for x in user_processes],p) for k,p in [('median',.5),('p90',.9),('max',1)]}})
    return budget,mapper,vma_rows,path_dirty,processes

def section_class(name):
    if name in LOADER_SECS or name.startswith('.gnu.version'):return 'loader_related'
    if name.startswith('.text'):return 'text'
    if name.startswith('.rodata'):return 'rodata'
    if name.startswith('.ARM.exidx') or name.startswith('.ARM.extab'):return 'arm_unwind'
    if name.startswith('.plt'):return 'plt'
    return 'code_other'

def code_budget(vmas,budget):
    sec=collections.defaultdict(lambda:collections.Counter())
    for r in rows(SRC/'section_residency.tsv'):
        sec[r['path']][section_class(r['section'])]+=float(r['resident_kB'])
    rx=collections.Counter()
    for v in vmas:
        if v['path'].startswith('/') and v['perms'].startswith('r-x'):rx[v['path']]+=int(v['Pss_kB'])
    totals=collections.Counter();file_rows=[]
    for path,pss in rx.items():
        summed=sum(sec[path].values())
        shares={k:(pss*v/summed if summed else 0.0) for k,v in sec[path].items()}
        if summed==0:shares['code_other']=float(pss)
        elif abs(sum(shares.values())-pss)>0.01:raise RuntimeError('code PSS attribution failed '+path)
        totals.update(shares)
        file_rows.append({'path':path,'rx_Pss_kB':pss,'unique_section_resident_kB':round(summed,5),
                          'loader_related_Pss_kB':round(shares.get('loader_related',0),5),
                          'text_Pss_kB':round(shares.get('text',0),5),
                          'rodata_Pss_kB':round(shares.get('rodata',0),5),
                          'arm_unwind_Pss_kB':round(shares.get('arm_unwind',0),5),
                          'plt_Pss_kB':round(shares.get('plt',0),5),
                          'other_Pss_kB':round(shares.get('code_other',0),5),
                          'loader_unique_kB':round(sec[path].get('loader_related',0),5)})
    write_tsv('code_file_pss.tsv',sorted(file_rows,key=lambda x:-x['rx_Pss_kB']))
    put_json('code_budget.json',{'rx_Pss_kB':budget['code_rx'],'classified_Pss_kB':dict(totals),
                                 'coverage_file_count':len(rx),'sum_check_kB':sum(totals.values())})
    return totals,file_rows

def parse_readelf(path,file):
    cmd=[str(READELF),'-hW','-SW','-dW','-Wr','--dyn-syms','-W',str(file)]
    result=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,errors='replace',timeout=180)
    text=result.stdout
    sections=[];relocs=[];symbols={};needed=[];soname='';flags='';flags1='';
    part='';relsec='';etype=''
    for line in text.splitlines():
        if line.strip().startswith('Type:') and not etype:etype=line.strip().split(':',1)[1].strip().split()[0]
        m=SEC.match(line)
        if m:
            sections.append({'name':m[1],'kind':m[2],'addr':int(m[3],16),'offset':int(m[4],16),
                             'size':int(m[5],16),'flags':m[6]})
        if '(NEEDED)' in line:
            m=re.search(r'\[(.*?)\]',line)
            if m:needed.append(m[1])
        if '(SONAME)' in line:
            m=re.search(r'\[(.*?)\]',line)
            if m:soname=m[1]
        if '(FLAGS)' in line:flags=line.strip()
        if '(FLAGS_1)' in line:flags1=line.strip()
        if line.startswith("Relocation section '"):
            relsec=line.split("'",2)[1];part='reloc';continue
        if line.startswith("Symbol table '.dynsym'"):
            part='dynsym';continue
        if line.startswith("Symbol table '"):
            part='other_sym';continue
        if part=='reloc':
            m=REL.match(line)
            if m and relsec.startswith(('.rel.','.rela.')) and not relsec.startswith(('.rel.debug','.rela.debug')):
                info=int(m[2],16)
                relocs.append({'section':relsec,'offset':int(m[1],16),'type':m[3],'symidx':info>>8})
        elif part=='dynsym':
            m=SYM.match(line)
            if m:
                symbols[int(m[1])]={'value':int(m[2],16),'size':int(m[3],16 if m[3].startswith('0x') else 10),'kind':m[4],
                                   'bind':m[5],'vis':m[6],'ndx':m[7],'name':m[8].split()[0] if m[8] else ''}
    return result.returncode,result.stderr,sections,relocs,symbols,needed,soname,flags,flags1,etype

def find_section(sections,addr):
    candidates=[s for s in sections if s['size'] and 'A' in s['flags'] and s['addr']<=addr<s['addr']+s['size']]
    return min(candidates,key=lambda x:(x['kind']=='NOBITS',x['size'])) if candidates else None

def reloc_class(t):
    for value in ('RELATIVE','ABS32','GLOB_DAT','JUMP_SLOT'):
        if t.endswith(value):return value
    return 'other'

def elf_analysis(mapper,vmas,path_dirty):
    elfroot=SRC/'elf';files={}
    for p in elfroot.rglob('*'):
        if not p.is_file() or p.is_symlink():continue
        with p.open('rb') as stream:
            if stream.read(4)!=b'\x7fELF':continue
        files['/'+str(p.relative_to(elfroot))]=p
    all_paths=sorted(files)
    records=[];section_rows=[];rel_by_file=[];page_rows=[];small=[];errors=[]
    process_names=collections.defaultdict(set)
    for v in vmas:
        if v['path'].startswith('/') and LIB.search(v['path']):process_names[int(v['pid'])].add(v['path'])
    total_type=collections.Counter();page_weight=collections.Counter();symbolic=collections.Counter()
    class_pages=collections.Counter();raw_targets=0;reloc_stream=gzip.open(OUT/'relocation_targets.tsv.gz','wt',newline='')
    rel_fields=['path','reloc_section','target_vaddr','target_file_offset','target_section','target_page','type','symbol_index','symbol_name','symbol_kind','symbol_bind','symbol_visibility','symbol_defined','container_class']
    rw=csv.DictWriter(reloc_stream,rel_fields,delimiter='\t',lineterminator='\n');rw.writeheader()
    for ix,path in enumerate(all_paths,1):
        try:rc,stderr,sections,relocs,symbols,needed,soname,flags,flags1,etype=parse_readelf(path,files[path])
        except Exception as ex:rc=124;stderr=repr(ex);sections=[];relocs=[];symbols={};needed=[];soname='';flags='';flags1='';etype=''
        if rc:errors.append({'path':path,'rc':rc,'stderr':stderr})
        byname={s['name']:s for s in sections}
        count=collections.Counter(reloc_class(r['type']) for r in relocs)
        for k,v in count.items():total_type[k]+=v
        defined_global=sum(s['ndx']!='UND' and s['bind']=='GLOBAL' and bool(s['name']) for s in symbols.values())
        defined_weak=sum(s['ndx']!='UND' and s['bind']=='WEAK' and bool(s['name']) for s in symbols.values())
        undef=sum(s['ndx']=='UND' and bool(s['name']) for s in symbols.values())
        row={'path':path,'ELF_type':etype,'PIE':int('PIE' in flags1),'BIND_NOW':int('BIND_NOW' in flags or 'NOW' in flags1),
             'DT_FLAGS':flags,'DT_FLAGS_1':flags1,
             'DT_NEEDED_count':len(needed),'DT_NEEDED':';'.join(needed),'SONAME':soname,
             'defined_GLOBAL':defined_global,'defined_WEAK':defined_weak,'undefined':undef,
             'reloc_RELATIVE':count['RELATIVE'],'reloc_ABS32':count['ABS32'],
             'reloc_GLOB_DAT':count['GLOB_DAT'],'reloc_JUMP_SLOT':count['JUMP_SLOT'],
             'reloc_other':count['other'],'mapped_processes':len(mapper.get(path,set())),'readelf_rc':rc}
        for name in ('.dynsym','.dynstr','.gnu.hash','.hash','.rel.dyn','.rel.plt','.data.rel.ro','.text'):
            row[name+'_bytes']=byname.get(name,{}).get('size',0)
        records.append(row)
        for s in sections:section_rows.append({'path':path,'section':s['name'],'vaddr':s['addr'],'file_offset':s['offset'],
                                                'size_bytes':s['size'],'flags':s['flags'],'type':s['kind']})
        containers=sorted((s['value'],s['value']+s['size'],s['name']) for s in symbols.values()
                          if s['ndx']!='UND' and s['size']>0 and s['kind']=='OBJECT')
        starts=[x[0] for x in containers]
        pages=collections.defaultdict(lambda:{'types':set(),'sections':set(),'targets':set(),'container':set()})
        bound=collections.Counter()
        for rel in relocs:
            s=find_section(sections,rel['offset']);sym=symbols.get(rel['symidx'],{})
            container='unknown'
            if s and s['name']=='.data.rel.ro' and containers:
                j=bisect.bisect_right(starts,rel['offset'])-1
                if j>=0 and rel['offset']<containers[j][1]:
                    name=containers[j][2]
                    if name.startswith('_ZTV'):container='vtable'
                    elif name.startswith('_ZTI'):container='typeinfo'
                    else:container='other_named_object'
            fileoff=(s['offset']+rel['offset']-s['addr']) if s and s['kind']!='NOBITS' else None
            page=(fileoff//4096) if fileoff is not None else None
            rw.writerow({'path':path,'reloc_section':rel['section'],'target_vaddr':hex(rel['offset']),
                         'target_file_offset':fileoff if fileoff is not None else '',
                         'target_section':s['name'] if s else '', 'target_page':page if page is not None else '',
                         'type':rel['type'],'symbol_index':rel['symidx'],'symbol_name':sym.get('name',''),
                         'symbol_kind':sym.get('kind',''),'symbol_bind':sym.get('bind',''),
                         'symbol_visibility':sym.get('vis',''),
                         'symbol_defined':int(sym.get('ndx','UND')!='UND'),'container_class':container})
            if s and fileoff is not None and 'W' in s['flags']:
                entry=pages[page];entry['types'].add(reloc_class(rel['type']));entry['sections'].add(s['name'])
                entry['targets'].add(fileoff);entry['container'].add(container)
                if rel['type'] in ('R_ARM_JUMP_SLOT','R_ARM_GLOB_DAT') and sym.get('ndx','UND')!='UND' and sym.get('kind')=='FUNC' and sym.get('vis')=='DEFAULT' and sym.get('bind') in ('GLOBAL','WEAK'):
                    bound[reloc_class(rel['type'])]+=1
            raw_targets+=1
        symbolic.update(bound)
        mapped=len(mapper.get(path,set()));islib=bool(LIB.search(path))
        eager_pages={pg for pg,details in pages.items() if row['BIND_NOW'] or details['types']!={'JUMP_SLOT'}}
        predicted=len(pages)*4*mapped
        eager_predicted=len(eager_pages)*4*mapped
        observed=sum(path_dirty.get((pid,path),0) for pid in mapper.get(path,set()))
        byclass=collections.Counter();smallpage=0
        for pg,details in pages.items():
            countbytes=4*len(details['targets'])
            if countbytes<256:smallpage+=1
            for cl in details['container']:
                if cl in ('vtable','typeinfo'):byclass[cl]+=1
            page_rows.append({'path':path,'page_file_offset':pg*4096,'target_count':len(details['targets']),
                              'target_bytes_upper':countbytes,'byte_fraction':round(countbytes/4096,6),
                              'sections':';'.join(sorted(details['sections'])),
                              'types':';'.join(sorted(details['types'])),
                              'container_classes':';'.join(sorted(details['container'])),
                              'mapped_processes':mapped,'weighted_kB':4*mapped,
                              'eager_or_nonplt':int(pg in eager_pages)})
        if islib:
            page_weight['all_library_pages_kB']+=predicted
            page_weight['eager_or_nonplt_library_pages_kB']+=eager_predicted
            page_weight['vtable_upper_kB']+=byclass['vtable']*4*mapped
            page_weight['typeinfo_upper_kB']+=byclass['typeinfo']*4*mapped
            page_weight['small_target_lt256_kB']+=smallpage*4*mapped
        rel_by_file.append({'path':path,'is_library':int(islib),'mapped_processes':mapped,
                            'predicted_file_dirty_kB':predicted,'eager_or_nonplt_predicted_kB':eager_predicted,
                            'observed_file_dirty_kB':observed,
                            'error_kB':predicted-observed,'writable_relocation_pages':len(pages),
                            'eager_or_nonplt_pages':len(eager_pages),
                            'vtable_pages':byclass['vtable'],'typeinfo_pages':byclass['typeinfo'],
                            'small_target_lt256_pages':smallpage,'Bsymbolic_function_candidate_relocs':sum(bound.values())})
        if islib and 1<=len(pages)<=2 and mapped:
            small.append({'path':path,'pages_per_process':len(pages),'process_count':mapped,
                          'weighted_kB':predicted,'process_ids':';'.join(map(str,sorted(mapper[path])))})
        if ix%25==0:log(f'readelf {ix}/{len(all_paths)} relocations {raw_targets}')
    reloc_stream.close()
    write_tsv('elf_metrics.tsv',records)
    write_tsv('elf_sections_vaddr.tsv',section_rows)
    write_tsv('relocation_pages.tsv',page_rows)
    write_tsv('relocation_model_by_file.tsv',rel_by_file)
    write_tsv('readelf_errors.tsv',errors,['path','rc','stderr'])
    # Exact co-mapping groups use identical PID sets in this one snapshot.
    grouping=collections.defaultdict(list)
    for item in small:grouping[tuple(sorted(mapper[item['path']]))].append(item['path'])
    gid={path:f'group_{i}' for i,paths in enumerate((v for v in grouping.values() if len(v)>1),1) for path in paths}
    for item in small:item['exact_mapper_group']=gid.get(item['path'],'')
    write_tsv('small_library_top50.tsv',sorted(small,key=lambda x:(-x['process_count'],-x['weighted_kB'],x['path']))[:50])
    write_tsv('small_library_comapping_groups.tsv',[{'group':f'group_{i}','libraries':';'.join(v),'process_count':len(k)}
          for i,(k,v) in enumerate(((k,v) for k,v in grouping.items() if len(v)>1),1)],
          ['group','libraries','process_count'])
    library_rows=[r for r in rel_by_file if r['is_library'] and r['mapped_processes']]
    pred=sum(r['predicted_file_dirty_kB'] for r in library_rows)
    eager=sum(r['eager_or_nonplt_predicted_kB'] for r in library_rows)
    obs=sum(r['observed_file_dirty_kB'] for r in library_rows)
    put_json('relocation_summary.json',{'mapped_ELF_count':sum(r['mapped_processes']>0 for r in records),
      'ELF_copies':len(records),'total_relocation_types':dict(total_type),'library_prediction_kB':pred,
      'library_eager_or_nonplt_prediction_kB':eager,
      'library_observed_file_r--_rw-_Private_Dirty_kB':obs,'signed_error_kB':pred-obs,
      'absolute_error_kB':sum(abs(r['error_kB']) for r in library_rows),
      'absolute_percentage_error_vs_observed':sum(abs(r['error_kB']) for r in library_rows)/obs if obs else None,
      'vtable_typeinfo_page_upper_kB':dict(page_weight),
      'Bsymbolic_function_candidate_relocs':dict(symbolic),
      'readelf_errors':len(errors),'dynamic_relocations_parsed':raw_targets})
    return records,section_rows,page_rows,rel_by_file,small

def code_pages_top50(section_rows):
    sec=collections.defaultdict(list)
    for s in section_rows:
        if s['section'].startswith('.text') and s['size_bytes']:
            sec[s['path']].append((int(s['file_offset']),int(s['file_offset'])+int(s['size_bytes'])))
    page_lists=collections.defaultdict(list)
    with gzip.open(SRC/'unique_pages.tsv.gz','rt') as f:
        for r in csv.DictReader(f,delimiter='\t'):
            page_lists[r['path']].append(int(r['file_offset_bytes']))
    rank=sorted(rows(SRC/'file_residency.tsv'),key=lambda r:-float(r['LLVM_unique_rx_Rss_kB'] or 0))[:50]
    out=[]
    for r in rank:
        path=r['path'];offsets=sorted(set(page_lists.get(path,[])));ranges=sec.get(path,[])
        text_pages=[off for off in offsets if any(off<s1 and off+4096>s0 for s0,s1 in ranges)]
        runs=[]
        for off in text_pages:
            if not runs or off!=runs[-1][-1]+4096:runs.append([off])
            else:runs[-1].append(off)
        gaps=[(b-a)//4096-1 for a,b in zip(text_pages,text_pages[1:])]
        text_size=sum(b-a for a,b in ranges)
        out.append({'path':path,'unique_rx_kB':r['LLVM_unique_rx_Rss_kB'],'text_bytes':text_size,
                    'text_resident_pages':len(text_pages),'text_residency_fraction':round(len(text_pages)*4096/text_size,5) if text_size else '',
                    'contiguous_runs':len(runs),'longest_run_pages':max(map(len,runs),default=0),
                    'mean_gap_pages':round(statistics.mean(gaps),3) if gaps else 0,
                    'hypothetical_25pct_hot_min_pages':math.ceil(.25*len(text_pages)),
                    'hypothetical_50pct_hot_min_pages':math.ceil(.5*len(text_pages))})
    write_tsv('code_top50_pages.tsv',out)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    log('START offline budget')
    budget,mapper,vmas,path_dirty,procs=smaps_budget()
    code,file_rows=code_budget(vmas,budget)
    if '--budget-only' in sys.argv:
        log('DONE budget-only refresh')
        return
    records,secs,pages,relfiles,small=elf_analysis(mapper,vmas,path_dirty)
    code_pages_top50(secs)
    log('DONE')

if __name__=='__main__':
    status='成功'
    try:main()
    except BaseException as ex:
        status='失败';log('ERROR '+repr(ex));raise
    finally:print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态='+status,flush=True)
