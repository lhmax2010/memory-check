#!/usr/bin/env python3
"""Classify saved smaps for the published fixed 94 identities, without board access."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import gzip
import io
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from datetime import datetime

ROOT=Path(__file__).resolve().parents[2]
PREV=ROOT/'memdiff/scripts/nopie_memory_delta_reconciliation.py'
spec=importlib.util.spec_from_file_location('reconcile_previous',PREV)
prev=importlib.util.module_from_spec(spec);spec.loader.exec_module(prev)
VMA=prev.VMA
METRIC=re.compile(r'^(Pss|SwapPss|Private_Dirty|Shared_Clean|Rss):\s+(\d+)\s+kB$')
FIELDS=('Pss','SwapPss','Private_Dirty','Shared_Clean','Rss')
CLASSES=('file_exec','file_readonly','file_writable','file_other','stack','anonymous','special')

def now():return datetime.now().astimezone().isoformat()
def dec(x):return Decimal(str(x))
def sha(path):return prev.sha256(path)
def tsv(path,rows,fields):prev.tsv(path,rows,fields)
def read(path):return prev.read_tsv(path)

def classify(path,perms):
    """Exactly one main class; addresses are never used for cross-image pairing."""
    if path=='[stack]' or path.startswith(('[stack:','[tstack')):return 'stack'
    if path.startswith(('/dev/','/proc/','/sys/','/kdbus-','/SYSV','memfd:','/memfd:')) or (path.startswith('[') and not path.startswith(('[heap]','[anon]','[anon:'))):
        return 'special'
    if path.startswith('/'):
        if len(perms)>2 and perms[2]=='x':return 'file_exec'
        if len(perms)>1 and perms[1]=='w':return 'file_writable'
        if perms.startswith('r'):return 'file_readonly'
        return 'file_other'
    return 'anonymous'

def is_file_class(cat):return cat.startswith('file_')

def parse_selected(lines,boot,pid,key,source):
    rows=[];active=None;missing=0
    def flush():
        nonlocal active,missing
        if active is None:return
        if 'Pss' not in active or 'SwapPss' not in active:
            missing+=1
        else:
            active['category']=classify(active['path'],active['perms'])
            active['Pss_plus_SwapPss_kB']=active['Pss']+active['SwapPss']
            rows.append(active)
        active=None
    for raw in lines:
        line=raw.rstrip('\r\n')
        m=VMA.match(line)
        if m:
            flush()
            parts=line.split(None,5)
            active={'boot':boot,'pid':pid,'identity_key':key,'start':m[1], 'end':m[2],
                    'perms':m[3],'offset':m[4],'device':parts[3], 'inode':parts[4],
                    'path':m[5],'source':source}
            continue
        m=METRIC.match(line)
        if m and active is not None:active[m[1]]=int(m[2])
    flush()
    return rows,missing

def historical_selected(entry,selected):
    boot=entry['label'];path=ROOT/entry['smaps'];output=[];seen=set();bad=[]
    active_pid=None;lines=[]
    def flush():
        nonlocal active_pid,lines
        if active_pid is None:return
        key=selected[active_pid]
        rows,missing=parse_selected(lines,boot,active_pid,key,entry['smaps'])
        output.extend(rows);seen.add(active_pid)
        if missing:bad.append((active_pid,missing))
        lines=[]
    with gzip.open(path,'rt',errors='replace') as stream:
        for line in stream:
            if line.startswith('### '):
                flush();parts=line.rstrip('\r\n').split(' ',3)
                active_pid=int(parts[1]) if len(parts)>2 and parts[1].isdigit() and int(parts[1]) in selected else None
            elif active_pid is not None:lines.append(line)
        flush()
    if seen!=set(selected):raise ValueError(f'{boot}: selected PID coverage missing {sorted(set(selected)-seen)}')
    if bad:raise ValueError(f'{boot}: missing metrics {bad}')
    return output

def new_selected(entry,selected):
    boot=entry['label'];collection=(ROOT/entry['collection']).parent;output=[]
    for pid,key in sorted(selected.items()):
        path=collection/'raw'/f'process_{pid}.stdout'
        lines=[];inside=False;saw_end=False
        with path.open(errors='replace') as stream:
            for raw in stream:
                line=raw.rstrip('\r\n')
                if line=='__SMAPS_BEGIN__':inside=True;continue
                if line=='__SMAPS_END__':saw_end=True;break
                if inside:lines.append(raw)
        if not saw_end:raise ValueError(f'{boot}:{pid} smaps incomplete')
        rows,missing=parse_selected(lines,boot,pid,key,str(path.relative_to(ROOT)))
        if missing:raise ValueError(f'{boot}:{pid} {missing} VMAs missing Pss/SwapPss')
        output.extend(rows)
    return output

def aggregate_process(rows,source_ledger):
    by=defaultdict(list)
    for row in rows:by[(row['boot'],row['pid'])].append(row)
    result=[]
    for boot,pid in sorted(by):
        maps=by[(boot,pid)];orig=source_ledger[(boot,pid)]
        p=sum(x['Pss'] for x in maps);s=sum(x['SwapPss'] for x in maps)
        if p!=dec(orig['Pss_kB']) or s!=dec(orig['SwapPss_kB']):
            raise ValueError(f'process conservation {boot}:{pid} {p}/{s} != {orig["Pss_kB"]}/{orig["SwapPss_kB"]}')
        rec={'boot':boot,'pid':pid,'name':orig['name'],'exe':orig['exe'],'identity_key':orig['identity_key'],
             'Pss_kB':p,'SwapPss_kB':s,'total_kB':p+s,'vma_count':len(maps)}
        for cat in CLASSES:
            rec[cat+'_Pss_kB']=sum(x['Pss'] for x in maps if x['category']==cat)
            rec[cat+'_SwapPss_kB']=sum(x['SwapPss'] for x in maps if x['category']==cat)
            rec[cat+'_total_kB']=rec[cat+'_Pss_kB']+rec[cat+'_SwapPss_kB']
        if sum(rec[c+'_total_kB'] for c in CLASSES)!=p+s:raise ValueError(f'category conservation {boot}:{pid}')
        result.append(rec)
    return result

def aggregate_files(rows):
    by=defaultdict(list)
    for row in rows:
        if is_file_class(row['category']):by[(row['boot'],row['path'])].append(row)
    result=[]
    for (boot,path),maps in sorted(by.items()):
        inodes={(m['device'],m['inode']) for m in maps}
        if len(inodes)>1:
            raise ValueError(f'{boot}:{path} maps multiple device/inode identities: {sorted(inodes)}')
        users=defaultdict(int)
        for m in maps:users[m['identity_key']]+=m['Pss_plus_SwapPss_kB']
        rec={'boot':boot,'path':path,'device':maps[0]['device'],'inode':maps[0]['inode'],
             'users_C':len(users),'largest_C_user':max(users,key=users.get),
             'largest_C_user_kB':max(users.values()),'Pss_kB':sum(m['Pss'] for m in maps),
             'SwapPss_kB':sum(m['SwapPss'] for m in maps)}
        rec['total_kB']=rec['Pss_kB']+rec['SwapPss_kB']
        for cat in ('file_exec','file_readonly','file_writable','file_other'):
            rec[cat+'_Pss_kB']=sum(m['Pss'] for m in maps if m['category']==cat)
            rec[cat+'_SwapPss_kB']=sum(m['SwapPss'] for m in maps if m['category']==cat)
            rec[cat+'_total_kB']=rec[cat+'_Pss_kB']+rec[cat+'_SwapPss_kB']
        for metric in ('Private_Dirty','Shared_Clean','Rss'):
            rec[metric+'_kB']=sum(m[metric] for m in maps) if all(metric in m for m in maps) else None
        if rec['total_kB']!=sum(rec[c+'_total_kB'] for c in ('file_exec','file_readonly','file_writable','file_other')):
            raise ValueError(f'file classification failed {boot}:{path}')
        result.append(rec)
    return result

def compare(rows,key_field,metrics):
    idx={(r['boot'],r[key_field]):r for r in rows}
    keys={r[key_field] for r in rows};output=[]
    for base in ('GCC','LLVM3'):
        for key in sorted(keys):
            boots=(base+'1',base+'2','noPIE1','noPIE2')
            objects=[idx.get((b,key)) for b in boots]
            values=[dec(r['total_kB']) if r else Decimal(0) for r in objects]
            if key_field=='identity_key' and any(r is None for r in objects):
                raise ValueError(f'fixed C identity absent {key}')
            rec={'comparison':'noPIE_minus_'+base,key_field:key,
                 'base1_total_kB':values[0],'base2_total_kB':values[1],
                 'new1_total_kB':values[2],'new2_total_kB':values[3],
                 'base_mean_kB':(values[0]+values[1])/2,'new_mean_kB':(values[2]+values[3])/2,
                 'base_range_kB':abs(values[1]-values[0]),'new_range_kB':abs(values[3]-values[2]),
                 'delta_total_kB':(values[2]+values[3]-values[0]-values[1])/2,
                 'interval':'separated_up' if min(values[2:])>max(values[:2]) else
                    'separated_down' if max(values[2:])<min(values[:2]) else 'overlap',
                 'base1_present':int(objects[0] is not None),'base2_present':int(objects[1] is not None),
                 'new1_present':int(objects[2] is not None),'new2_present':int(objects[3] is not None)}
            for metric in metrics:
                vals=[dec(r[metric]) if r else Decimal(0) for r in objects]
                rec['delta_'+metric]=(vals[2]+vals[3]-vals[0]-vals[1])/2
                if key_field=='path':
                    for i,b in enumerate(boots):rec[b+'_'+metric]=vals[i]
            if key_field=='path':
                for b,r in zip(boots,objects):
                    rec[b+'_users_C']=int(r['users_C']) if r else 0
                    rec[b+'_largest_C_user']=r['largest_C_user'] if r else 'not_mapped_in_C'
            output.append(rec)
    return output

def main_run(manifest_path,out):
    manifest=json.loads(manifest_path.read_text());out.mkdir(parents=True,exist_ok=True)
    olddir=ROOT/'memdiff/data/noPIE_memory_delta_reconciliation'
    old_inputs={r['label']:r for r in read(olddir/'inputs.tsv')}
    old_raw={(r['boot'],int(r['pid'])):r for r in read(olddir/'new_image_raw_files.tsv')}
    old_ledger=list(read(olddir/'process_ledger.tsv'))
    all_ledger={(r['boot'],int(r['pid'])):r for r in old_ledger}
    strict={(r['name'],r['exe']) for r in read(olddir/'fixed94_identities.tsv')}
    if len(strict)!=94:raise ValueError('published fixed identity list changed')
    for entry in manifest['snapshots']:
        label=entry['label'];p=ROOT/entry.get('smaps',entry.get('collection'))
        if sha(p)!=old_inputs[label]['primary_sha256']:raise ValueError(f'primary input drift {label}')
        budget=entry.get('process_budget')
        if budget and sha(ROOT/budget)!=old_inputs[label]['budget_sha256']:raise ValueError(f'budget input drift {label}')
    selected=defaultdict(dict);source_ledger={}
    argot_paths={'/usr/apps/com.samsung.tizen.argot/bin/argot',
       '/opt/usr/share/argot/.local/bin/tsr','/opt/usr/share/argot/.local/bin/tsr-bwrap'}
    for r in old_ledger:
        if r['set']=='C' or (r['set']=='R' and r['exe'] in argot_paths):
            boot=r['boot'];pid=int(r['pid']);selected[boot][pid]=r['identity_key'];source_ledger[(boot,pid)]=r
    for entry in manifest['snapshots']:
        if entry['kind']!='image_budget':continue
        collection=(ROOT/entry['collection']).parent
        for pid in selected[entry['label']]:
            ref=old_raw[(entry['label'],pid)]
            if sha(collection/'raw'/f'process_{pid}.stdout')!=ref['sha256']:
                raise ValueError(f'raw process drift {entry["label"]}:{pid}')
    progress=out/'progress.log'
    maps=[]
    for entry in manifest['snapshots']:
        label=entry['label'];print(now(),'parse',label,flush=True)
        recs=historical_selected(entry,selected[label]) if entry['kind']=='historical_smaps' else new_selected(entry,selected[label])
        maps.extend(recs)
        with progress.open('a') as f:f.write(f'{now()} {label} {len(recs)} VMAs\n')
    # The same mapped object can occur in more than one process; preserve each VMA.
    processes=aggregate_process(maps,source_ledger)
    cproc=[r for r in processes if (r['name'],r['exe']) in strict]
    argot=[r for r in processes if r['exe'] in argot_paths]
    if len(cproc)!=94*6:raise ValueError('fixed C process coverage mismatch')
    ckeys={(r['boot'],r['identity_key']) for r in cproc}
    if len(ckeys)!=len(cproc):raise ValueError('duplicate C identity in a boot')
    cmaps=[m for m in maps if (source_ledger[(m['boot'],m['pid'])]['name'],source_ledger[(m['boot'],m['pid'])]['exe']) in strict]
    files=aggregate_files(cmaps)
    expected={r['boot']:dec(r['C_kB']) for r in read(olddir/'six_snapshots.tsv')}
    checks={}
    for boot in expected:
        c=[r for r in cproc if r['boot']==boot]
        bycat={cat:sum((r[cat+'_total_kB'] for r in c),Decimal(0)) for cat in CLASSES}
        total=sum((r['total_kB'] for r in c),Decimal(0))
        file_total=sum((r['total_kB'] for r in files if r['boot']==boot),Decimal(0))
        category_file=sum(bycat[cat] for cat in CLASSES if is_file_class(cat))
        if total!=expected[boot] or sum(bycat.values())!=total or file_total!=category_file:
            raise ValueError(f'boot conservation {boot}: {total}/{expected[boot]}/{file_total}/{category_file}')
        checks[boot]={'C_kB':str(total),'category_error_kB':str(sum(bycat.values())-total),
                      'file_error_kB':str(file_total-category_file),'categories_kB':{k:str(v) for k,v in bycat.items()},
                      'VMA_count_C':sum(r['vma_count'] for r in c),'C_processes':len(c)}
    pmetrics=['Pss_kB','SwapPss_kB']+[cat+'_total_kB' for cat in CLASSES]
    proccomp=compare(cproc,'identity_key',pmetrics)
    fmetrics=['Pss_kB','SwapPss_kB']+[cat+'_total_kB' for cat in ('file_exec','file_readonly','file_writable','file_other')]
    filecomp=compare(files,'path',fmetrics)
    # Category and identity comparisons must sum to published delta C.
    for base in ('GCC','LLVM3'):
        name='noPIE_minus_'+base
        expected_delta=dec(next(r['delta_C_kB'] for r in read(olddir/'comparisons.tsv') if r['comparison']==name))
        got=sum((r['delta_total_kB'] for r in proccomp if r['comparison']==name),Decimal(0))
        if got!=expected_delta:raise ValueError(f'process comparison {name}: {got}!={expected_delta}')
    # Gzip only derived mapping rows; raw smaps are never copied.
    mfields=['boot','pid','identity_key','start','end','perms','offset','device','inode','path','category','Pss','SwapPss',
             'Pss_plus_SwapPss_kB','Private_Dirty','Shared_Clean','Rss','source']
    with (out/'classified_vmas.tsv.gz').open('wb') as binary:
        with gzip.GzipFile(fileobj=binary,mode='wb',filename='',mtime=0) as compressed:
            with io.TextIOWrapper(compressed,encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,mfields,delimiter='\t',lineterminator='\n',extrasaction='ignore');w.writeheader()
                for m in maps:w.writerow({k:m.get(k,'NA') for k in mfields})
    tsv(out/'C_processes_six.tsv',cproc,list(cproc[0]))
    tsv(out/'C_process_comparisons.tsv',proccomp,list(proccomp[0]))
    tsv(out/'C_files_per_boot.tsv',files,list(files[0]))
    tsv(out/'C_file_comparisons.tsv',filecomp,list(dict.fromkeys(k for row in filecomp for k in row)))
    tsv(out/'argot_processes_six.tsv',argot,list(argot[0]))
    # Keep absence from a measured list distinct from the six unresolved PIDs
    # in each new-image capture. Parentage is taken only from saved status.
    audit=[]
    for entry in manifest['snapshots']:
        boot=entry['label'];source=(ROOT/entry['collection']).parent if entry['kind']=='image_budget' else None
        for exe in sorted(argot_paths):
            matches=[r for r in argot if r['boot']==boot and r['exe']==exe]
            if not matches:
                audit.append({'boot':boot,'exe':exe,'capture_state':'not_in_measured_ledger',
                              'instances':0,'Pss_kB':0,'SwapPss_kB':0,'total_kB':0,
                              'pids':'','parent_evidence':'no same-snapshot parent record'})
                continue
            parents=[]
            for item in matches:
                raw=(source/'raw'/f'process_{item["pid"]}.stdout').read_text(errors='replace') if source else ''
                match=re.search(r'^PPid:\s*(\d+)\s*$',raw,re.M)
                ppid=int(match.group(1)) if match else None
                parent=all_ledger.get((boot,ppid)) if ppid is not None else None
                parents.append(f'{item["pid"]}<-{ppid if ppid is not None else "unknown"}'
                               + (f' {parent["identity_key"]}' if parent else ' parent identity unavailable in selected ledger'))
            audit.append({'boot':boot,'exe':exe,'capture_state':'measured',
                          'instances':len(matches),'Pss_kB':sum(r['Pss_kB'] for r in matches),
                          'SwapPss_kB':sum(r['SwapPss_kB'] for r in matches),
                          'total_kB':sum(r['total_kB'] for r in matches),
                          'pids':','.join(str(r['pid']) for r in matches),'parent_evidence':'; '.join(parents)})
    tsv(out/'argot_capture_audit.tsv',audit,list(audit[0]))
    for kind,records in (('process',proccomp),('file',filecomp)):
        top=[]
        for base in ('GCC','LLVM3'):
            positives=sorted((r for r in records if r['comparison']=='noPIE_minus_'+base and r['delta_total_kB']>0),
                             key=lambda r:-r['delta_total_kB'])[:20]
            top.extend(positives)
        tsv(out/f'top20_{kind}_positive.tsv',top,list(top[0]) if top else ['comparison'])
    (out/'validation.json').write_text(json.dumps({'status':'PASS','input_manifest_sha256':sha(manifest_path),
      'fixed94_sha256':sha(olddir/'fixed94_identities.tsv'),'checks':checks,
      'selected_processes':len(processes),'selected_C_processes':len(cproc),'classified_VMA_rows':len(maps),
      'files_per_boot_rows':len(files),'missing_primary_fields':0},ensure_ascii=False,indent=2)+'\n')
    print(now(),'validation PASS',len(maps),'VMAs',flush=True)

def main():
    a=argparse.ArgumentParser();a.add_argument('--manifest',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    x=a.parse_args();status='成功'
    try:main_run(x.manifest,x.out)
    except Exception:status='失败';raise
    finally:print('已结束',now(),'状态='+status,flush=True)
if __name__=='__main__':main()
