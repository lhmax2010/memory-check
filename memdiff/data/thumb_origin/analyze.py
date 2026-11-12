#!/usr/bin/env python3
"""Offline ARM/Thumb origin inventory and same-library size comparisons."""
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
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
MEM=HERE.parents[1]
SYSTEM=MEM/'data/system_code_page_sections'
BUDGET=MEM/'data/llvm_memory_budget'
THUMB=MEM/'data/extra_levers_sizing/thumb_coverage.tsv'
BIN=Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin')
READELF=BIN/'armv7l-tizen-linux-gnueabi-readelf'
OBJDUMP=BIN/'armv7l-tizen-linux-gnueabi-objdump'
ENV={**os.environ,'LD_LIBRARY_PATH':str(BIN.parent/'lib64')}
SEC=re.compile(r'^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+\S+\s+([A-Z]*)')
INSN=re.compile(r'^\s*[0-9a-f]+:\s+((?:[0-9a-f]{2,8}\s*)+)\s+(.+)$',re.I)
ASM_FEATURE=re.compile(r'(_neon|_armv6|_asm)',re.I)
NEON_OP=re.compile(r'^v(?:ld[1-4]|st[1-4]|(?:q|r)?[a-z0-9]+\.(?:i|u|s|p)\d+)',re.I)
Q_REGISTER=re.compile(r'\bq\d+\b',re.I)


def progress(msg):
    line=datetime.datetime.now().astimezone().isoformat()+' '+msg
    with (HERE/'progress.log').open('a') as f:f.write(line+'\n')
    print(line,flush=True)


def read_tsv(path):
    with path.open(newline='') as f:yield from csv.DictReader(f,delimiter='\t')


def write_tsv(name,rows,fields):
    with (HERE/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n',extrasaction='ignore')
        w.writeheader();w.writerows(rows)


def run(argv,timeout=180):
    return subprocess.run([str(x) for x in argv],stdin=subprocess.DEVNULL,capture_output=True,
                          text=True,errors='replace',env=ENV,timeout=timeout)


def decode(rawfile,mode):
    cmd=[OBJDUMP,'-D','-b','binary','-m','arm','-EL']
    if mode=='thumb':cmd+=['-M','force-thumb']
    result=run(cmd+[rawfile],timeout=30)
    valid=0;invalid=0;vector=0;instr=0
    for line in result.stdout.splitlines():
        m=INSN.match(line)
        if not m:continue
        n=len(''.join(m[1].split()))//2
        mnemonic=m[2].strip().split()[0].lower() if m[2].strip() else ''
        bad=(not mnemonic or mnemonic.startswith('.') or 'undefined' in m[2].lower() or
             'unpredictable' in m[2].lower() or mnemonic=='(bad)')
        if bad:invalid+=n
        else:
            valid+=n;instr+=1
            if NEON_OP.match(mnemonic) or Q_REGISTER.search(m[2]):vector+=1
    return {'rc':result.returncode,'legal_fraction':valid/(valid+invalid) if valid+invalid else 0,
            'valid_bytes':valid,'invalid_bytes':invalid,'vector_instructions':vector,
            'instruction_count':instr,'stderr':result.stderr.strip()[:160]}


def symbols_and_properties(path,rawout):
    file=SYSTEM/'elf'/path.lstrip('/')
    outputs={}
    for label,args in (('comment',['-p','.comment']),('attributes',['-A']),
                       ('sections',['-SW']),('segments',['-lW']),('symbols',['--dyn-syms','-W'])):
        res=run([READELF,*args,file])
        outputs[label]=res.stdout
        rawout.write(json.dumps({'path':path,'kind':label,'rc':res.returncode,
                                 'stdout':res.stdout,'stderr':res.stderr},ensure_ascii=False)+'\n')
        if res.returncode and label!='comment':
            raise RuntimeError(f'readelf {label} {path}: {res.stderr[:300]}')
    comment=outputs['comment']
    compiler='both' if 'clang' in comment.lower() and 'gcc' in comment.lower() else 'clang' if 'clang' in comment.lower() else 'gcc' if 'gcc' in comment.lower() else 'none'
    sections=[]
    for line in outputs['sections'].splitlines():
        m=SEC.match(line)
        if m:sections.append({'name':m[1],'kind':m[2],'vaddr':int(m[3],16),
                              'offset':int(m[4],16),'size':int(m[5],16),'flags':m[6]})
    text=next((s for s in sections if s['name']=='.text'),None)
    rodata=sum(s['size'] for s in sections if s['name'].startswith('.rodata') and s['kind']!='NOBITS')
    rx_load=0
    for line in outputs['segments'].splitlines():
        parts=line.split()
        if len(parts)>=8 and parts[0]=='LOAD' and 'E' in parts[6:-1]:
            rx_load+=int(parts[4],16)
    funcs=[];names=[];in_dyn=False
    for line in outputs['symbols'].splitlines():
        if line.startswith("Symbol table '.dynsym'"):
            in_dyn=True;continue
        if line.startswith('Symbol table '):in_dyn=False
        if not in_dyn:continue
        parts=line.split()
        if len(parts)<8 or not parts[0].endswith(':') or not parts[0][:-1].isdigit():continue
        kind,bind,vis,ndx,name=parts[3:8]
        if ndx=='UND':continue
        if kind=='FUNC':
            try:value=int(parts[1],16);size=int(parts[2],16 if parts[2].startswith('0x') else 10)
            except ValueError:continue
            funcs.append((value&~1,(value&~1)+size,'thumb' if value&1 else 'arm',name,size))
        if name:names.append(name)
    funcs.sort()
    attrs=[line.strip() for line in outputs['attributes'].splitlines() if line.strip().startswith('Tag_')]
    asm_names=sorted({name for name in names if ASM_FEATURE.search(name)})
    return {'compiler':compiler,'comment':comment.strip() or '未找到',
            'attributes':' | '.join(attrs) if attrs else '未找到',
            'sections':sections,'text':text,'rodata_bytes':rodata,'rx_load_bytes':rx_load,
            'funcs':funcs,'asm_names':asm_names,'defined_func_count':len(funcs)}


def sample_mode(symbols,vaddr,arm,thumb):
    arm_vote=0;thumb_vote=0
    for first,last,mode,name,size in symbols:
        if size and first<vaddr+256 and last>vaddr:
            overlap=max(0,min(last,vaddr+256)-max(first,vaddr))
            if mode=='arm':arm_vote+=overlap
            else:thumb_vote+=overlap
    if arm_vote>=128 and arm_vote>=2*thumb_vote:return 'arm','symbol_range'
    if thumb_vote>=128 and thumb_vote>=2*arm_vote:return 'thumb','symbol_range'
    diff=arm['legal_fraction']-thumb['legal_fraction']
    if diff>=.15:return 'arm','legal_fraction'
    if diff<=-.15:return 'thumb','legal_fraction'
    return 'unknown','ambiguous'


def sample_file(path,prop,tempfile_path,sample_writer):
    sec=prop['text']
    if not sec or not sec['size']:
        return {'samples':0,'arm_samples':0,'thumb_samples':0,'unknown_samples':0,
                'estimated_arm_text_fraction':'未确定','vector_sample_fraction':'未确定',
                'symbol_range_decisions':0,'legal_fraction_decisions':0}
    file=SYSTEM/'elf'/path.lstrip('/')
    size=sec['size'];first_page=sec['offset']//4096
    last_page=(sec['offset']+size-1)//4096
    pages=[first_page+round(i*(last_page-first_page)/63) for i in range(64)]
    starts=sorted({max(sec['offset'],page*4096) for page in pages})
    result=collections.Counter();vector_segments=0;known=0
    with file.open('rb') as stream:
        for index,start in enumerate(starts):
            stream.seek(start)
            payload=stream.read(min(256,sec['offset']+size-start))
            if len(payload)<4:continue
            tempfile_path.write_bytes(payload)
            arm=decode(tempfile_path,'arm');thumb=decode(tempfile_path,'thumb')
            vaddr=sec['vaddr']+(start-sec['offset'])
            chosen,reason=sample_mode(prop['funcs'],vaddr,arm,thumb)
            result[chosen]+=1;result[reason]+=1
            if chosen!='unknown':
                known+=1
                if (arm if chosen=='arm' else thumb)['vector_instructions']:
                    vector_segments+=1
            sample_writer.writerow({'path':path,'sample':index,'file_offset':start,'vaddr':hex(vaddr),
                'bytes':len(payload),'ARM_legal_fraction':round(arm['legal_fraction'],4),
                'Thumb_legal_fraction':round(thumb['legal_fraction'],4),'ARM_vector_insns':arm['vector_instructions'],
                'Thumb_vector_insns':thumb['vector_instructions'],'chosen_mode':chosen,'reason':reason,
                'arm_rc':arm['rc'],'thumb_rc':thumb['rc']})
    total=result['arm']+result['thumb']+result['unknown']
    symbol_arm=sum(1 for f in prop['funcs'] if f[2]=='arm')/len(prop['funcs']) if prop['funcs'] else 0
    fraction=(result['arm']+result['unknown']*symbol_arm)/total if total else None
    return {'samples':total,'arm_samples':result['arm'],'thumb_samples':result['thumb'],
            'unknown_samples':result['unknown'],
            'estimated_arm_text_fraction':round(fraction,6) if fraction is not None else '未确定',
            'vector_sample_fraction':round(vector_segments/known,6) if known else '未确定',
            'symbol_range_decisions':result['symbol_range'],
            'legal_fraction_decisions':result['legal_fraction']}


def path_category(path):
    if path.startswith('/prd/'):return '/prd'
    if path.startswith('/opt/usr/apps/'):return '/opt/usr/apps'
    if path.startswith('/usr/local/'):return '/usr/local'
    if path.startswith('/hal/'):return '/hal'
    if path.startswith('/usr/lib/'):return '/usr/lib'
    if path.startswith('/usr/bin/'):return '/usr/bin'
    return 'other'


def origin_class(prop,path):
    vector=prop['vector_sample_fraction']
    known=prop['arm_samples']+prop['thumb_samples']
    if (vector!='未确定' and known>=8 and vector>=.10 and vector*known>=3) or len(prop['asm_names'])>=5:
        return 'asm_or_NEON_performance_sensitive'
    if path_category(path) in ('/prd','/opt/usr/apps','/usr/local','/hal'):
        return 'vendor_or_app_prebuilt_source_unknown'
    if prop['compiler']=='gcc':return 'GCC_comment_only'
    if prop['compiler']=='clang':return 'clang_comment_only_ARM_mode'
    return 'undetermined'


def main():
    HERE.mkdir(parents=True,exist_ok=True)
    progress('START Thumb origin offline sizing')
    coverage={r['path']:r for r in read_tsv(THUMB)}
    scope={p:('ARM_gt80' if float(r['ARM_percent'])>80 else 'mixed_20_80')
           for p,r in coverage.items() if r['ARM_percent'] and (float(r['ARM_percent'])>80 or 20<=float(r['ARM_percent'])<=80)}
    if collections.Counter(scope.values())!={'ARM_gt80':106,'mixed_20_80':12}:
        raise RuntimeError(f'unexpected scope {collections.Counter(scope.values())}')
    metrics={r['path']:r for r in read_tsv(BUDGET/'elf_metrics.tsv')}
    code={r['path']:r for r in read_tsv(BUDGET/'code_file_pss.tsv')}
    residence={r['path']:r for r in read_tsv(SYSTEM/'files_from_pages.tsv')}
    file_pss=collections.Counter();dirty_ro=collections.Counter();dirty_rw=collections.Counter()
    for r in read_tsv(BUDGET/'vmas_all.tsv'):
        path=r['path']
        if path not in scope:continue
        file_pss[path]+=int(r['Pss_kB'])
        if r['perms'].startswith('r--'):dirty_ro[path]+=int(r['Private_Dirty_kB'])
        if r['perms'].startswith('rw-'):dirty_rw[path]+=int(r['Private_Dirty_kB'])
    properties={};sample_rows=[]
    sample_fields=['path','sample','file_offset','vaddr','bytes','ARM_legal_fraction','Thumb_legal_fraction',
                   'ARM_vector_insns','Thumb_vector_insns','chosen_mode','reason','arm_rc','thumb_rc']
    raw_path=HERE/'readelf_raw.jsonl.gz'
    with gzip.open(raw_path,'wt') as raw, (HERE/'sample_disassembly.tsv').open('w',newline='') as sample_file_out, tempfile.TemporaryDirectory(prefix='thumb_origin_') as tmp:
        writer=csv.DictWriter(sample_file_out,sample_fields,delimiter='\t',lineterminator='\n')
        writer.writeheader()
        temp=Path(tmp)/'snippet.bin'
        for index,path in enumerate(sorted(scope),1):
            prop=symbols_and_properties(path,raw)
            prop.update(sample_file(path,prop,temp,writer))
            prop['origin_class']=origin_class(prop,path)
            properties[path]=prop
            if index%5==0:progress(f'ELF/disassembly {index}/{len(scope)}')
    rows=[]
    for path in sorted(scope):
        p=properties[path];m=metrics[path];c=code.get(path,{})
        rows.append({'path':path,'scope':scope[path],'path_category':path_category(path),
            'compiler_marker':p['compiler'],'comment_full':p['comment'].replace('\n','\\n'),
            'ARM_attributes_full':p['attributes'],'ARM_dynsym_percent':coverage[path]['ARM_percent'],
            'ARM_text_fraction_estimate':p['estimated_arm_text_fraction'],
            'samples':p['samples'],'arm_samples':p['arm_samples'],'thumb_samples':p['thumb_samples'],
            'unknown_samples':p['unknown_samples'],'symbol_range_decisions':p['symbol_range_decisions'],
            'legal_fraction_decisions':p['legal_fraction_decisions'],
            'vector_sample_fraction':p['vector_sample_fraction'],'asm_feature_symbol_count':len(p['asm_names']),
            'asm_feature_names':';'.join(p['asm_names'][:30]),'SONAME':m['SONAME'],
            'text_kB':round(p['text']['size']/1024,6) if p['text'] else 0,
            'rodata_kB':round(p['rodata_bytes']/1024,6),'rx_LOAD_kB':round(p['rx_load_bytes']/1024,6),
            'unique_rx_kB':int(residence.get(path,{}).get('unique_Rss_kB',0)),
            'file_Pss_kB':file_pss[path],'rx_Pss_kB':float(c.get('rx_Pss_kB',0) or 0),
            'rx_loader_Pss_kB':float(c.get('loader_related_Pss_kB',0) or 0),
            'rx_text_Pss_kB':float(c.get('text_Pss_kB',0) or 0),
            'rx_rodata_Pss_kB':float(c.get('rodata_Pss_kB',0) or 0),
            'rx_arm_unwind_Pss_kB':float(c.get('arm_unwind_Pss_kB',0) or 0),
            'rx_plt_Pss_kB':float(c.get('plt_Pss_kB',0) or 0),
            'rx_other_Pss_kB':float(c.get('other_Pss_kB',0) or 0),
            'r--_Private_Dirty_kB':dirty_ro[path],'rw-_Private_Dirty_kB':dirty_rw[path],
            'mapped_processes':m['mapped_processes'],'defined_FUNC_exports':p['defined_func_count'],
            'origin_class':p['origin_class']})
    bypath={r['path']:r for r in rows}
    # Find any same SONAME or basename ARM/Thumb pairing, including Thumb files outside the 118-file scope.
    keys=collections.defaultdict(set)
    for path,r in coverage.items():
        for key in (Path(path).name,metrics[path]['SONAME']):
            if key:keys[key].add(path)
    pairset=set()
    for path in scope:
        if scope[path]!='ARM_gt80':continue
        for key in (Path(path).name,metrics[path]['SONAME']):
            if not key:continue
            for other in keys[key]:
                if other!=path and coverage[other]['ARM_percent'] and float(coverage[other]['ARM_percent'])<20:
                    pairset.add((path,other))
    partners=collections.defaultdict(list)
    for arm_path,thumb_path in sorted(pairset):partners[arm_path].append(thumb_path)
    for row in rows:row['thumb_partner_paths']=';'.join(partners.get(row['path'],[])) or '未找到'
    write_tsv('file_properties.tsv',rows,list(rows[0]))
    pair_rows=[]
    with gzip.open(HERE/'pair_readelf_raw.jsonl.gz','wt') as raw:
        for arm_path,thumb_path in sorted(pairset):
            arm=properties[arm_path]
            thumb=symbols_and_properties(thumb_path,raw)
            def ratio(a,b):return round(b/a,6) if a else '未确定'
            counts_match=arm['defined_func_count']==thumb['defined_func_count']
            pair_rows.append({'arm_path':arm_path,'thumb_path':thumb_path,
                'match_key':Path(arm_path).name if Path(arm_path).name==Path(thumb_path).name else metrics[arm_path]['SONAME'],
                'arm_text_kB':round(arm['text']['size']/1024,6) if arm['text'] else 0,
                'thumb_text_kB':round(thumb['text']['size']/1024,6) if thumb['text'] else 0,
                'text_thumb_over_arm':ratio(arm['text']['size'] if arm['text'] else 0,thumb['text']['size'] if thumb['text'] else 0),
                'arm_rodata_kB':round(arm['rodata_bytes']/1024,6),
                'thumb_rodata_kB':round(thumb['rodata_bytes']/1024,6),
                'rodata_thumb_over_arm':ratio(arm['rodata_bytes'],thumb['rodata_bytes']),
                'arm_rx_LOAD_kB':round(arm['rx_load_bytes']/1024,6),
                'thumb_rx_LOAD_kB':round(thumb['rx_load_bytes']/1024,6),
                'rx_LOAD_thumb_over_arm':ratio(arm['rx_load_bytes'],thumb['rx_load_bytes']),
                'arm_defined_FUNC':arm['defined_func_count'],'thumb_defined_FUNC':thumb['defined_func_count'],
                'export_count_matches':int(counts_match),'version_comparable':int(counts_match)})
    pair_fields=['arm_path','thumb_path','match_key','arm_text_kB','thumb_text_kB','text_thumb_over_arm',
        'arm_rodata_kB','thumb_rodata_kB','rodata_thumb_over_arm','arm_rx_LOAD_kB','thumb_rx_LOAD_kB',
        'rx_LOAD_thumb_over_arm','arm_defined_FUNC','thumb_defined_FUNC','export_count_matches','version_comparable']
    write_tsv('arm_thumb_pairs.tsv',pair_rows,pair_fields)
    categories=collections.defaultdict(list)
    for row in rows:categories[row['origin_class']].append(row)
    class_rows=[]
    for name in ('vendor_or_app_prebuilt_source_unknown','GCC_comment_only','clang_comment_only_ARM_mode',
                 'asm_or_NEON_performance_sensitive','undetermined'):
        subset=categories[name]
        class_rows.append({'class':name,'files':len(subset),'text_kB':round(sum(float(r['text_kB']) for r in subset),3),
            'unique_rx_kB':sum(int(r['unique_rx_kB']) for r in subset),
            'file_Pss_kB':sum(int(r['file_Pss_kB']) for r in subset)})
    write_tsv('class_summary.tsv',class_rows,list(class_rows[0]))
    ratios=[float(p['text_thumb_over_arm']) for p in pair_rows if p['text_thumb_over_arm']!='未确定']
    median=statistics.median(ratios) if ratios else None
    estimates=[];to_check=[]
    for name in ('GCC_comment_only','clang_comment_only_ARM_mode'):
        subset=categories[name]
        to_check.extend(subset)
        text=sum(float(r['text_kB']) for r in subset)
        resident=sum(int(r['unique_rx_kB']) for r in subset)
        estimates.append({'class':name,'files':len(subset),'text_kB':round(text,3),
            'unique_rx_kB':resident,'reference_ratio':round(median,6) if median is not None else '未确定',
            'estimated_text_reduction_kB':round(text*(1-median),3) if median is not None else '未确定',
            'estimated_resident_reduction_kB':round(resident*(1-median),3) if median is not None else '未确定',
            'quality':'样本不足且导出 FUNC 数不同，仅跨版本参考推算' if len(pair_rows)<3 or any(not int(p['export_count_matches']) for p in pair_rows) else '同名配对参考推算'})
    write_tsv('ratio_estimates.tsv',estimates,list(estimates[0]))
    to_check.sort(key=lambda r:-int(r['file_Pss_kB']))
    (HERE/'to_check_paths.txt').write_text(''.join(r['path']+'\n' for r in to_check))
    summary={'scope_counts':dict(collections.Counter(scope.values())),'file_classes':class_rows,
        'pair_count':len(pair_rows),'pair_text_ratio_median':median,
        'pair_text_ratio_range':[min(ratios),max(ratios)] if ratios else None,
        'export_count_equal_pairs':sum(int(p['export_count_matches']) for p in pair_rows),
        'ratio_estimates':estimates,'to_check_top10':[r['path'] for r in to_check[:10]],
        'sample_total':sum(int(p['samples']) for p in properties.values()),
        'sample_ambiguous_total':sum(int(p['unknown_samples']) for p in properties.values())}
    (HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    checks={'scope_106_plus_12':len(rows)==118,
        'category_count_sums':sum(r['files'] for r in class_rows)==118,
        'all_scope_elf_present':all((SYSTEM/'elf'/p.lstrip('/')).is_file() for p in scope),
        'sample_rows_match':sum(int(p['samples']) for p in properties.values())==sum(1 for _ in read_tsv(HERE/'sample_disassembly.tsv')),
        'pair_count_consistent':len(pair_rows)==len(pairset)}
    (HERE/'qa.json').write_text(json.dumps(checks,indent=2)+'\n')
    if not all(checks.values()):raise RuntimeError(f'QA failed: {checks}')
    progress('DONE Thumb origin offline sizing')


if __name__=='__main__':
    status='成功'
    try:main()
    except BaseException as exc:
        status='失败';progress('ERROR '+repr(exc));raise
    finally:print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态='+status,flush=True)
