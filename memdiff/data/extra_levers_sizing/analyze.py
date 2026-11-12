#!/usr/bin/env python3
"""Offline sizing of relative tables, read-ahead, duplicate ELF and Thumb coverage."""
import collections
import csv
import datetime
import gzip
import hashlib
import itertools
import json
import re
import statistics
import struct
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
MEM=HERE.parents[1]
SYS=MEM/'data/system_code_page_sections'
BUD=MEM/'data/llvm_memory_budget'
READELF=Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf')
LLVM=Path('/home/linhao/clang-toolchains/src/llvm-project-22.1.8.src/llvm')
LOG=HERE/'progress.log'
POINTER={'string_pointer_candidate','other_function_pointer_candidate'}


def progress(message):
    line=datetime.datetime.now().astimezone().isoformat()+' '+message
    with LOG.open('a') as f:f.write(line+'\n')
    print(line,flush=True)


def read(path):
    with path.open(newline='') as f:yield from csv.DictReader(f,delimiter='\t')


def write(name,records,fields):
    with (HERE/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n',extrasaction='ignore')
        w.writeheader();w.writerows(records)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def source_evidence():
    names=['include/llvm/CodeGen/BasicTTIImpl.h','lib/Transforms/Utils/RelLookupTableConverter.cpp',
           'lib/Passes/PassBuilderPipelines.cpp']
    rows=[]
    with (HERE/'llvm22_source_excerpt.txt').open('w') as dst:
        for name in names:
            path=LLVM/name
            if not path.is_file():raise RuntimeError(f'missing LLVM source {path}')
            rows.append({'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size})
            dst.write(f'===== {path} sha256={rows[-1]["sha256"]} =====\n')
            for index,line in enumerate(path.read_text(errors='replace').splitlines(),1):
                relevant=(name.endswith('BasicTTIImpl.h') and 636<=index<=659 or
                          name.endswith('RelLookupTableConverter.cpp') and (29<=index<=130 or 206<=index<=247) or
                          name.endswith('PassBuilderPipelines.cpp') and 1666<=index<=1675)
                if relevant:dst.write(f'{index}: {line}'.rstrip()+'\n')
            dst.write('\n')
    excerpt=HERE/'llvm22_source_excerpt.txt'
    excerpt.write_text(excerpt.read_text().rstrip()+'\n')
    write('source_files.tsv',rows,['path','sha256','bytes'])


def parse_elf_inventory():
    files={r['path']:r for r in read(BUD/'elf_metrics.tsv')}
    residence={r['path']:r for r in read(SYS/'files_from_pages.tsv')}
    export_ranges=collections.defaultdict(list)
    symbol_rows=[];errors=[]
    for index,(path,metric) in enumerate(files.items(),1):
        file=SYS/'elf'/path.lstrip('/')
        if not file.is_file():
            errors.append({'path':path,'error':'ELF copy missing'});continue
        result=subprocess.run([str(READELF),'-A','--dyn-syms','-W',str(file)],
                              stdin=subprocess.DEVNULL,capture_output=True,text=True,errors='replace',timeout=180)
        if result.returncode:
            errors.append({'path':path,'error':result.stderr.strip()[:500]});continue
        attrs=[];defined=collections.Counter();undefined=collections.Counter();in_dyn=False
        for line in result.stdout.splitlines():
            if 'Tag_THUMB_ISA_use:' in line or 'Tag_ARM_ISA_use:' in line or 'Tag_CPU_arch:' in line:
                attrs.append(line.strip())
            if line.startswith("Symbol table '.dynsym'"):
                in_dyn=True;continue
            if line.startswith('Symbol table '):in_dyn=False
            if not in_dyn:continue
            parts=line.split()
            if len(parts)<8 or not parts[0].endswith(':') or not parts[0][:-1].isdigit():continue
            try:value=int(parts[1],16);size=int(parts[2],16 if parts[2].startswith('0x') else 10)
            except ValueError:continue
            kind,bind,vis,ndx,name=parts[3:8]
            if kind=='FUNC':
                (undefined if ndx=='UND' else defined)['thumb' if value&1 else 'arm']+=1
            if ndx!='UND' and bind in ('GLOBAL','WEAK') and vis in ('DEFAULT','PROTECTED'):
                export_ranges[path].append((value&~1, (value&~1)+size, name, size))
        arm=defined['arm'];thumb=defined['thumb'];count=arm+thumb
        symbol_rows.append({'path':path,'text_kB':round(float(metric['.text_bytes'])/1024,3),
            'unique_rx_kB':residence.get(path,{}).get('unique_Rss_kB',''),
            'defined_FUNC_ARM':arm,'defined_FUNC_Thumb':thumb,'defined_FUNC_total':count,
            'ARM_percent':round(100*arm/count,4) if count else '',
            'undefined_FUNC':sum(undefined.values()),'ARM_attributes':' | '.join(attrs) if attrs else '未找到'})
        if index%100==0:progress(f'ELF attributes/symbols {index}/{len(files)}')
    write('thumb_coverage.tsv',symbol_rows,list(symbol_rows[0]))
    write('readelf_errors.tsv',errors,['path','error'])
    qualified=[r for r in symbol_rows if r['defined_FUNC_total'] and float(r['ARM_percent'])>20 and float(r['text_kB'])>256]
    qualified.sort(key=lambda r:-float(r['text_kB']))
    write('arm_mode_large_text.tsv',qualified,list(symbol_rows[0]))
    return files,residence,export_ranges,symbol_rows,qualified,errors


def exported_overlap(exports,start,end):
    for first,last,name,size in exports:
        if (size and first<end and last>start) or (not size and start<=first<end):
            return True
    return False


def candidate_array_analysis(files,exports):
    arrays=[];path_counts=collections.Counter();page_part=collections.defaultdict(set);page_whole=collections.defaultdict(set)
    string_targets=collections.defaultdict(list)
    with gzip.open(BUD/'relro_target_classification.tsv.gz','rt',newline='') as src:
        reader=csv.DictReader(src,delimiter='\t')
        for index,(path,group) in enumerate(itertools.groupby(reader,key=lambda r:r['path']),1):
            offsets={}
            for row in group:
                off=row['target_file_offset']
                if not off:continue
                key=int(off)
                old=offsets.get(key)
                if old is None or row['classification'] in POINTER:
                    offsets[key]=row
            ordered=sorted(offsets)
            if not ordered:continue
            runs=[];run=[]
            for off in ordered:
                if run and off!=run[-1]+4:
                    runs.append(run);run=[]
                run.append(off)
            if run:runs.append(run)
            mapped=int(files.get(path,{}).get('mapped_processes',0))
            for run in runs:
                if len(run)<4:continue
                candidate=[off for off in run if offsets[off]['classification'] in POINTER]
                if len(candidate)/len(run)<.75:continue
                start_v=int(offsets[run[0]]['target_vaddr'],16)
                end_v=int(offsets[run[-1]]['target_vaddr'],16)+4
                if exported_overlap(exports.get(path,[]),start_v,end_v):continue
                string=[off for off in candidate if offsets[off]['classification']=='string_pointer_candidate']
                funcs=len(candidate)-len(string)
                pages={off//4096 for off in candidate}
                whole_this_run=set()
                for page in pages:
                    page_part[path].add(page)
                    page_start=page*4096
                    if page_start>=run[0] and page_start+4096<=run[-1]+4 and len(candidate)==len(run):
                        page_whole[path].add(page)
                        whole_this_run.add(page)
                path_counts[path]+=len(string)
                string_targets[path].extend(string[:5])
                arrays.append({'path':path,'start_vaddr':hex(start_v),'end_vaddr_exclusive':hex(end_v),
                    'start_file_offset':run[0],'end_file_offset_exclusive':run[-1]+4,
                    'entries':len(run),'string_candidates':len(string),'function_candidates':funcs,
                    'candidate_percent':round(100*len(candidate)/len(run),2),'mapped_processes':mapped,
                    'pages_with_candidate':len(pages),
                    'whole_pages_in_this_run':len(whole_this_run)})
            if index%100==0:progress(f'candidate array files {index}')
    fields=['path','start_vaddr','end_vaddr_exclusive','start_file_offset','end_file_offset_exclusive','entries',
            'string_candidates','function_candidates','candidate_percent','mapped_processes','pages_with_candidate','whole_pages_in_this_run']
    write('candidate_arrays.tsv',arrays,fields)
    by_file=[]
    for path in sorted(set(page_part)|set(page_whole)):
        mapped=int(files[path]['mapped_processes'])
        by_file.append({'path':path,'mapped_processes':mapped,
            'pages_with_candidate':len(page_part[path]),'whole_pages':len(page_whole[path]),
            'any_upper_kB':4*len(page_part[path])*mapped,
            'whole_upper_kB':4*len(page_whole[path])*mapped})
    write('candidate_pages_by_file.tsv',by_file,
          ['path','mapped_processes','pages_with_candidate','whole_pages','any_upper_kB','whole_upper_kB'])
    partial_kB=sum(4*len(pages)*int(files[path]['mapped_processes']) for path,pages in page_part.items())
    whole_kB=sum(4*len(pages)*int(files[path]['mapped_processes']) for path,pages in page_whole.items())
    top=path_counts.most_common(3)
    return arrays,partial_kB,whole_kB,top,string_targets,page_part,page_whole


def string_examples(top,strings,arrays):
    sections=collections.defaultdict(list)
    for row in read(BUD/'elf_sections_vaddr.tsv'):
        sections[row['path']].append(row)
    results=[]
    for path,count in top:
        file=SYS/'elf'/path.lstrip('/')
        data=file.read_bytes()
        seen=set();samples=[]
        for off in strings[path]:
            if off in seen or off+4>len(data):continue
            seen.add(off)
            ptr=struct.unpack_from('<I',data,off)[0]
            text='未确定'
            for s in sections[path]:
                try:addr=int(s['vaddr']); size=int(s['size_bytes']); pos=int(s['file_offset'])
                except ValueError:continue
                if s['section'].startswith('.rodata') and addr<=ptr<addr+size:
                    p=pos+ptr-addr;end=data.find(b'\0',p,min(p+81,len(data)))
                    if end>p:text=data[p:end].decode('ascii',errors='replace')
                    break
            samples.append({'pointer_slot_file_offset':off,'pointee_vaddr':hex(ptr),'string':text})
            if len(samples)>=5:break
        subset=[r for r in arrays if r['path']==path and r['string_candidates']]
        results.append({'path':path,'candidate_count':count,'intervals':len(subset),
            'range_start':hex(min(int(r['start_vaddr'],16) for r in subset)) if subset else '',
            'range_end_exclusive':hex(max(int(r['end_vaddr_exclusive'],16) for r in subset)) if subset else '',
            'samples':samples})
    (HERE/'top3_string_arrays.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    return results


def contiguous_runs(offsets):
    values=sorted(set(offsets));runs=[];run=[]
    for off in values:
        if run and off!=run[-1]+4096:
            runs.append(run);run=[]
        run.append(off)
    if run:runs.append(run)
    return runs


def read_ahead_analysis(residence):
    ranked=sorted(residence.values(),key=lambda r:-int(r['unique_Rss_kB']))[:50]
    selected={r['path'] for r in ranked};pages=collections.defaultdict(list)
    with gzip.open(SYS/'unique_pages.tsv.gz','rt',newline='') as f:
        for r in csv.DictReader(f,delimiter='\t'):
            if r['path'] in selected:pages[r['path']].append(int(r['file_offset_bytes']))
    text_sec=collections.defaultdict(list)
    for r in read(BUD/'elf_sections_vaddr.tsv'):
        if r['path'] in selected and r['section'].startswith('.text'):
            text_sec[r['path']].append((int(r['file_offset']),int(r['file_offset'])+int(r['size_bytes'])))
    code={r['path']:r for r in read(BUD/'code_file_pss.tsv')}
    rows=[];all_runs=[];total_text=0;retained_proxy=0
    for path in selected:
        runs=contiguous_runs(pages[path]);all_runs.extend(runs)
        lengths=[len(x) for x in runs]
        txt=[off for off in pages[path] if any(off<e and off+4096>s for s,e in text_sec[path])]
        text_runs=contiguous_runs(txt)
        shortest=min((len(x) for x in text_runs),default=0)
        text_pss=float(code.get(path,{}).get('text_Pss_kB',0) or 0)
        total_text+=text_pss
        retained_proxy+=text_pss*shortest/len(txt) if txt else 0
        rows.append({'path':path,'unique_rx_kB':residence[path]['unique_Rss_kB'],
            'runs':len(runs),'resident_pages':len(pages[path]),'shortest_run_pages':min(lengths,default=0),
            'longest_run_pages':max(lengths,default=0),'runs_ge16':sum(x>=16 for x in lengths),
            'runs_ge32':sum(x>=32 for x in lengths),'text_resident_pages':len(txt),
            'text_shortest_run_pages':shortest,'text_Pss_kB':round(text_pss,6),
            'text_retained_shortest_run_proxy_kB':round(text_pss*shortest/len(txt),6) if txt else 0})
    write('top50_read_ahead.tsv',sorted(rows,key=lambda r:-int(r['unique_rx_kB'])),list(rows[0]))
    length_dist=collections.Counter()
    for run in all_runs:
        n=len(run)
        bin='1' if n==1 else '2-3' if n<=3 else '4-7' if n<=7 else '8-15' if n<=15 else '16-31' if n<=31 else '32-63' if n<=63 else '64+'
        length_dist[bin]+=1
    starts=[run[0]//4096 for run in all_runs]
    align={str(n):sum(x%n==0 for x in starts)/len(starts) if starts else 0 for n in (4,8,16,32)}
    long16=sum(len(run) for run in all_runs if len(run)>=16 and run[0]//4096%16==0)
    long32=sum(len(run) for run in all_runs if len(run)>=32 and run[0]//4096%32==0)
    all_pages=sum(map(len,all_runs))
    summary={'files':len(selected),'runs':len(all_runs),'pages':all_pages,'length_distribution':dict(length_dist),
             'start_alignment_fraction':align,'pages_in_16_aligned_runs_ge16':long16,
             'fraction_in_16_aligned_runs_ge16':long16/all_pages if all_pages else 0,
             'runs_exactly_16':sum(len(run)==16 for run in all_runs),
             'runs_exactly_32':sum(len(run)==32 for run in all_runs),
             'pages_in_32_aligned_runs_ge32':long32,
             'fraction_in_32_aligned_runs_ge32':long32/all_pages if all_pages else 0,
             'top50_text_Pss_kB':total_text,'shortest_run_retained_proxy_kB':retained_proxy,
             'hypothetical_saving_range_kB':[0,total_text-retained_proxy]}
    (HERE/'read_ahead_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def duplicates(residence):
    state=json.loads((SYS/'collection.json').read_text())
    byhash=collections.defaultdict(list)
    for entry in state['pulled']:
        if entry.get('is_elf') and entry.get('status')=='hash_match' and entry.get('host_sha256'):
            byhash[entry['host_sha256']].append(entry['path'])
    inode=collections.defaultdict(set)
    for r in read(SYS/'vmas.tsv'):
        inode[r['path']].add((r['dev'],r['inode']))
    pss={r['path']:float(r['rx_Pss_kB']) for r in read(BUD/'code_file_pss.tsv')}
    out=[];groups=[];ceiling=0
    for hashval,paths in sorted(byhash.items()):
        paths=[p for p in paths if p in residence]
        if len(paths)<2:continue
        # Drop paths that are only alternate names of the same mapped inode.
        unique=[];seen=set()
        for path in paths:
            keys=frozenset(inode[path])
            if keys and keys not in seen:
                unique.append(path);seen.add(keys)
        if len(unique)<2:continue
        vals=[int(residence[p]['unique_Rss_kB']) for p in unique]
        upper=sum(vals)-max(vals)
        ceiling+=upper
        group_id=len(groups)+1
        groups.append({'group':group_id,'sha256':hashval,'files':len(unique),'upper_saving_kB':upper})
        for path in unique:
            out.append({'group':group_id,'sha256':hashval,'path':path,'mapped_processes':residence[path]['mappers'],
                'unique_rx_kB':residence[path]['unique_Rss_kB'],'rx_Pss_sum_kB':pss.get(path,'未找到'),
                'dev_inode':';'.join(f'{dev}:{node}' for dev,node in sorted(inode[path]))})
    write('duplicate_elf_groups.tsv',groups,['group','sha256','files','upper_saving_kB'])
    write('duplicate_elf_paths.tsv',out,['group','sha256','path','mapped_processes','unique_rx_kB','rx_Pss_sum_kB','dev_inode'])
    return len(groups),ceiling


def main():
    HERE.mkdir(parents=True,exist_ok=True)
    progress('START extra levers offline sizing')
    source_evidence()
    files,residence,exports,symbols,qualified,errors=parse_elf_inventory()
    progress('ELF inventory complete')
    arrays,partial,whole,top,strings,page_part,page_whole=candidate_array_analysis(files,exports)
    examples=string_examples(top,strings,arrays)
    progress('candidate arrays complete')
    read_ahead=read_ahead_analysis(residence)
    progress('read-ahead analysis complete')
    duplicate_count,duplicate_upper=duplicates(residence)
    progress('duplicate ELF analysis complete')
    summary={'candidate_arrays':len(arrays),'candidate_page_any_kB':partial,'candidate_page_whole_kB':whole,
        'top3_string_libraries':examples,'read_ahead':read_ahead,'duplicate_groups':duplicate_count,
        'duplicate_upper_kB':duplicate_upper,'arm_mode_large_text_files':len(qualified),
        'arm_mode_large_text_top10':qualified[:10],'readelf_errors':errors}
    (HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    checks={
        'whole_pages_subset_any':all(page_whole[p] <= page_part[p] for p in page_whole),
        'whole_upper_not_above_any':whole<=partial,
        'run_bins_sum_to_runs':sum(read_ahead['length_distribution'].values())==read_ahead['runs'],
        'top50_count':read_ahead['files']==50,
        'all_elf_symbols_measured':len(symbols)==len(files),
        'readelf_no_errors':not errors,
        'duplicate_upper_nonnegative':duplicate_upper>=0,
    }
    (HERE/'qa.json').write_text(json.dumps(checks,indent=2)+'\n')
    if not all(checks.values()):raise RuntimeError(f'QA failed: {checks}')
    progress('DONE extra levers offline sizing')


if __name__=='__main__':
    status='成功'
    try:main()
    except BaseException as exc:
        status='失败';progress('ERROR '+repr(exc));raise
    finally:print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态='+status,flush=True)
