#!/usr/bin/env python3
"""Reconcile six saved smaps snapshots by the published fixed process identity set.

Only reads saved evidence.  The identity rule and the historical smaps VMA
expression are imported from the scripts used for the published noPIE report.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from decimal import Decimal
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT/'memdiff/data/noPIE_prelink_validation/historical_same_source.py'
spec = importlib.util.spec_from_file_location('historical_same_source', OLD)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
VMA = old.VMA
METRIC = re.compile(r'^(Pss|SwapPss):\s+(\d+)\s+kB$')
ONE = Decimal(1)


def now():
    return datetime.now().astimezone().isoformat()


def dec(value):
    return Decimal(str(value))


def tsv(path, rows, fields):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, delimiter='\t', lineterminator='\n', extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ('NA' if row.get(k) is None or row.get(k) == '' else row.get(k)) for k in fields})


def read_tsv(path):
    with path.open(newline='') as stream:
        yield from csv.DictReader(stream, delimiter='\t')


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def source_path(relative):
    if not relative:
        return None
    p = ROOT/relative
    if not p.is_file():
        raise FileNotFoundError(p)
    return p


def parse_smaps_lines(lines):
    """Return exact KiB and missing-field count for one smaps stream."""
    pss = swap = vmas = missing = 0
    current = None

    def flush():
        nonlocal pss, swap, vmas, missing, current
        if current is None:
            return
        vmas += 1
        if 'Pss' not in current or 'SwapPss' not in current:
            missing += 1
        else:
            pss += current['Pss']
            swap += current['SwapPss']
        current = None

    for line in lines:
        if VMA.match(line):
            flush()
            current = {}
            continue
        match = METRIC.match(line)
        if match and current is not None:
            current[match[1]] = int(match[2])
    flush()
    return {'Pss_kB': pss, 'SwapPss_kB': swap, 'vmas': vmas, 'missing_vmas': missing}


def historical_records(entry):
    path = source_path(entry['smaps'])
    records = []
    current = None
    metrics = []
    with gzip.open(path, 'rt', errors='replace') as stream:
        for line in stream:
            if line.startswith('### '):
                if current is not None:
                    current.update(parse_smaps_lines(metrics))
                    records.append(current)
                bits = line.rstrip('\r\n').split(' ', 3)
                if len(bits) < 3 or not bits[1].isdigit():
                    current = None
                else:
                    current = {'pid': int(bits[1]), 'name': bits[2], 'exe': bits[3] if len(bits)>3 else '',
                               'source': entry['smaps']}
                metrics = []
            elif current is not None:
                metrics.append(line)
        if current is not None:
            current.update(parse_smaps_lines(metrics))
            records.append(current)
    for record in records:
        if record['missing_vmas']:
            record['measurement_status'] = 'incomplete_missing_metric'
        elif record['vmas'] == 0 and not record['exe']:
            record['measurement_status'] = 'kernel_no_vma'
        elif record['vmas'] == 0:
            record['measurement_status'] = 'incomplete_no_vma'
        else:
            record['measurement_status'] = 'measured'
    return records, {'listed': len(records), 'incomplete_pids': [r['pid'] for r in records if r['measurement_status'].startswith('incomplete')],
                     'kernel_no_vma': sum(r['measurement_status']=='kernel_no_vma' for r in records)}


def raw_new_smaps(path):
    section = False
    lines = []
    with path.open(errors='replace') as stream:
        for raw in stream:
            line = raw.rstrip('\r\n')
            if line == '__SMAPS_BEGIN__':
                section = True
                continue
            if line == '__SMAPS_END__':
                section = False
                break
            if section:
                lines.append(line)
    return parse_smaps_lines(lines)


def new_records(entry):
    collection = source_path(entry['collection']).parent
    state = json.loads((collection/'collection.json').read_text())
    if state.get('status') != 'DONE':
        raise ValueError(f"incomplete collection {entry['label']}")
    status = {int(p['pid']):p['status'] for p in state['processes']}
    budget = list(read_tsv(source_path(entry['process_budget'])))
    records=[]
    for row in budget:
        pid=int(row['pid'])
        if status.get(pid) != 'complete':
            raise ValueError(f'budget includes incomplete PID {entry["label"]}:{pid}')
        raw=collection/'raw'/f'process_{pid}.stdout'
        measured=raw_new_smaps(raw)
        if measured['missing_vmas'] or measured['vmas']==0:
            raise ValueError(f'missing raw smaps fields {entry["label"]}:{pid}: {measured}')
        if measured['Pss_kB'] != dec(row['Pss_total_kB']) or measured['SwapPss_kB'] != dec(row['SwapPss_kB']):
            raise ValueError(f'raw/budget mismatch {entry["label"]}:{pid}: {measured} vs {row["Pss_total_kB"]}/{row["SwapPss_kB"]}')
        records.append({'pid':pid,'name':row['name'],'exe':row['exe'],'source':str(raw.relative_to(ROOT)),
                        **measured,'measurement_status':'measured'})
    if len({r['pid'] for r in records}) != len(records):
        raise ValueError(f'duplicate PID in budget {entry["label"]}')
    incomplete=[p['pid'] for p in state['processes'] if p['status']!='complete']
    for pid in incomplete:
        records.append({'pid':int(pid),'name':'','exe':'','source':str((collection/'raw'/f'process_{pid}.stdout').relative_to(ROOT)),
                        'Pss_kB':None,'SwapPss_kB':None,'vmas':0,'missing_vmas':0,
                        'measurement_status':'incomplete_not_captured'})
    return records, {'listed':len(state['processes']), 'incomplete_pids':incomplete,
                     'complete_without_measured_vma':sum(p['status']=='complete' for p in state['processes'])-len(records)}


def identity(record):
    name, exe = record['name'],record['exe']
    if not name or name=='NA' or not exe or exe=='NA' or not exe.startswith('/'):
        return None
    return name,exe


def strict_identity_set(path):
    rows=list(read_tsv(path))
    keys={(r['name'],r['exe']) for r in rows}
    byboot=Counter(r['boot'] for r in rows)
    if len(keys)!=94 or len(rows)!=94*6 or set(byboot.values())!={94}:
        raise ValueError(f'published strict set malformed: keys={len(keys)}, rows={len(rows)}, boots={byboot}')
    for r in rows:
        if not r['exe'].startswith('/'):
            raise ValueError(f'published key has unresolved exe: {r}')
    return keys, rows


def classify_status(record):
    if record['measurement_status'] != 'measured':
        return 'UNMEASURED'
    if identity(record) is None:
        return 'R_UNRESOLVED'
    return 'R'


def derive_partitions(boots, strict):
    ledger=[]
    for label, records in boots.items():
        pids=[r['pid'] for r in records]
        if len(pids)!=len(set(pids)):
            raise ValueError(f'duplicate PID in {label}')
        for record in records:
            kind=classify_status(record)
            key=identity(record)
            if kind=='R' and key in strict:
                kind='C'
            if record['measurement_status']=='kernel_no_vma':
                kind='EXCLUDED_KERNEL'
            val = record['Pss_kB']+record['SwapPss_kB'] if kind in ('C','R','R_UNRESOLVED') else None
            ledger.append({**record,'boot':label,'identity_key':' | '.join(key) if key else 'UNRESOLVED',
                           'set':kind,'total_kB':val})
    return ledger


def summarize_six(ledger, strict, previous):
    output=[]
    for label in ('GCC1','GCC2','LLVM31','LLVM32','noPIE1','noPIE2'):
        part=[r for r in ledger if r['boot']==label]
        c=[r for r in part if r['set']=='C']
        r=[r for r in part if r['set'] in ('R','R_UNRESOLVED')]
        if len(c)!=len(strict) or {identity(x) for x in c}!=strict:
            raise ValueError(f'fixed 94 absent/duplicate in {label}: instances={len(c)} identities={len({identity(x) for x in c})}')
        T=sum((x['total_kB'] for x in c+r),Decimal(0))
        C=sum((x['total_kB'] for x in c),Decimal(0))
        R=sum((x['total_kB'] for x in r),Decimal(0))
        if T!=C+R:
            raise ValueError(f'T != C+R: {label}')
        old=previous[label]
        output.append({'boot':label,'user_instances':len(c+r),'C_identities':len(strict),
          'R_instances':len(r),'T_kB':T,'C_kB':C,'R_kB':R,
          'published_T_kB':dec(old['all_Pss_SwapPss_kB']),
          'published_C_kB':dec(old['strict_common_Pss_SwapPss_kB']),
          'T_minus_published_kB':T-dec(old['all_Pss_SwapPss_kB']),
          'C_minus_published_kB':C-dec(old['strict_common_Pss_SwapPss_kB'])})
    return output


def mean2(a,b):
    return (a+b)/2


def image_summary(six):
    by={r['boot']:r for r in six}
    out=[]
    for image in ('GCC','LLVM3','noPIE'):
        a,b=by[f'{image}1'],by[f'{image}2']
        row={'image':image}
        for k in ('T','C','R'):
            x,y=a[f'{k}_kB'],b[f'{k}_kB']
            row.update({f'{k}1_kB':x,f'{k}2_kB':y,f'{k}_mean_kB':mean2(x,y),f'{k}_range_kB':abs(y-x)})
        out.append(row)
    return out


def compare_image(image_rows):
    by={r['image']:r for r in image_rows}; current=by['noPIE'];out=[]
    for base in ('GCC','LLVM3'):
        old=by[base]
        row={'comparison':f'noPIE_minus_{base}'}
        for k in ('T','C','R'):
            row[f'delta_{k}_kB']=current[f'{k}_mean_kB']-old[f'{k}_mean_kB']
        row['conservation_error_kB']=row['delta_T_kB']-row['delta_C_kB']-row['delta_R_kB']
        if row['conservation_error_kB']!=0:raise ValueError(f'delta conservation failed: {row}')
        out.append(row)
    return out


def remaining_contributions(ledger, coverage):
    """Account for observed R records; zero means no measured contribution.

    If capture had incomplete PIDs, absence is labelled unknown rather than
    being interpreted as a confirmed zero-memory process.
    """
    idx={}
    for boot in ('GCC1','GCC2','LLVM31','LLVM32','noPIE1','noPIE2'):
        grouped=defaultdict(list)
        for rec in ledger:
            if rec['boot']!=boot or rec['set'] not in ('R','R_UNRESOLVED'):
                continue
            key=identity(rec)
            if key is None:
                key=(f'UNRESOLVED:{boot}:{rec["pid"]}','UNRESOLVED')
            grouped[key].append(rec)
        idx[boot]=grouped
    rows=[]
    for base in ('GCC','LLVM3'):
        boots=(f'{base}1',f'{base}2','noPIE1','noPIE2')
        keys=set().union(*(idx[b] for b in boots))
        for key in sorted(keys):
            values=[];counts=[];statuses=[]
            for b in boots:
                group=idx[b].get(key,[])
                values.append(sum((r['total_kB'] for r in group),Decimal(0)))
                counts.append(len(group))
                statuses.append('present' if group else ('unknown_not_measured' if coverage[b]['incomplete_pids'] else 'absent_in_capture'))
            nbase=counts[0]+counts[1];nnew=counts[2]+counts[3]
            if key[1]=='UNRESOLVED': pattern='identity_unresolved'
            elif nbase and nnew:pattern='both_sides_observed_not_C'
            elif nnew:pattern='new_only_observed'
            else:pattern='baseline_only_observed'
            uncertain=any(s=='unknown_not_measured' for s in statuses)
            category='absence_unknown' if uncertain else pattern
            comparison=f'noPIE_minus_{base}'
            observed_base_mean=mean2(values[0],values[1])
            observed_new_mean=mean2(values[2],values[3])
            observed_delta=observed_new_mean-observed_base_mean
            true_base_mean=observed_base_mean if all(s!='unknown_not_measured' for s in statuses[:2]) else None
            true_new_mean=observed_new_mean if all(s!='unknown_not_measured' for s in statuses[2:]) else None
            true_delta=true_new_mean-true_base_mean if true_base_mean is not None and true_new_mean is not None else None
            safe_values=[None if status=='unknown_not_measured' else value for value,status in zip(values,statuses)]
            rows.append({'comparison':comparison,'name':key[0],'exe':key[1],
              'identity_key':' | '.join(key),'category':category,'observed_presence_pattern':pattern,
              'base1_kB':safe_values[0],'base2_kB':safe_values[1], 'new1_kB':safe_values[2],'new2_kB':safe_values[3],
              'base1_measured_kB':values[0],'base2_measured_kB':values[1],
              'new1_measured_kB':values[2],'new2_measured_kB':values[3],
              'base1_instances':counts[0],'base2_instances':counts[1],'new1_instances':counts[2],'new2_instances':counts[3],
              'base1_state':statuses[0],'base2_state':statuses[1],'new1_state':statuses[2],'new2_state':statuses[3],
              'base_mean_kB':true_base_mean,'new_mean_kB':true_new_mean,'delta_kB':true_delta,
              'observed_base_mean_kB':observed_base_mean,'observed_new_mean_kB':observed_new_mean,
              'observed_delta_kB':observed_delta,
              'instance_change':int(len(set(counts))>1),
              'comparability':'absence unresolved by incomplete capture' if uncertain else
                'same name+exe, workload unverified' if pattern=='both_sides_observed_not_C' else
                'identity unavailable' if pattern=='identity_unresolved' else 'one-sided measured population',
              'matching_basis':'comm + exe (no PID or command line)'})
    return rows


def category_summary(contrib):
    grouped=defaultdict(list)
    for row in contrib:grouped[(row['comparison'],row['category'])].append(row)
    output=[]
    for (comparison,category),rows in sorted(grouped.items()):
        output.append({'comparison':comparison,'category':category,'identity_count':len(rows),
          'base1_instances':sum(r['base1_instances'] for r in rows),
          'base2_instances':sum(r['base2_instances'] for r in rows),
          'new1_instances':sum(r['new1_instances'] for r in rows),
          'new2_instances':sum(r['new2_instances'] for r in rows),
          'observed_base_mean_kB':sum((r['observed_base_mean_kB'] for r in rows),Decimal(0)),
          'observed_new_mean_kB':sum((r['observed_new_mean_kB'] for r in rows),Decimal(0)),
          'observed_delta_kB':sum((r['observed_delta_kB'] for r in rows),Decimal(0)),
          'unknown_absence_identities':sum(any(r[f'{side}{n}_state']=='unknown_not_measured' for side in ('base','new') for n in (1,2)) for r in rows)})
    return output


def input_inventory(manifest, coverage, version):
    output=[]
    for entry in manifest['snapshots']:
        label=entry['label']; source=entry.get('smaps',entry.get('collection'))
        budget=entry.get('process_budget')
        if entry['kind']=='image_budget':
            state=json.loads(source_path(entry['collection']).read_text())
            build=state.get('build_id','unknown');bootid=state.get('identity',{}).get('boot_id','unknown')
            sample='exact_host_snapshot_time_not_recorded; collection_started='+state.get('started_utc','unknown')
            uptime=state.get('capture_uptime_s','unknown');stable=state.get('stable','unknown')
            capture=state.get('capture_reason','unknown')
        else:
            b=json.loads(source_path(entry['boot_metadata']).read_text())
            rm=source_path(entry['run_meta']).read_text()
            build='not_recorded_in_snapshot';bootid=b.get('boot_id','unknown')
            sample=source_path(entry['sample_time']).read_text().splitlines()[0]
            m=re.search(r'uptime:\s*([0-9.]+)',source_path(entry['sample_time']).read_text());uptime=m[1] if m else 'unknown'
            m=re.search(r'^steady=(.+)$',rm,re.M);stable=m[1] if m else 'unknown'
            capture='45-minute-limit' if stable=='no' else 'steady-criteria'
        output.append({'label':label,'image':entry['image'],'BUILD_ID':build,'boot_id':bootid,
          'sample_time':sample,'sample_uptime_s':uptime,'steady':stable,'capture_reason':capture,
          'primary_source':source,'primary_sha256':sha256(source_path(source)),
          'budget_source':budget or 'not_applicable','budget_sha256':sha256(source_path(budget)) if budget else 'not_applicable',
          'boot_metadata_source':entry.get('boot_metadata','not_applicable'),
          'boot_metadata_sha256':sha256(source_path(entry['boot_metadata'])) if entry.get('boot_metadata') else 'not_applicable',
          'run_meta_source':entry.get('run_meta','not_applicable'),
          'run_meta_sha256':sha256(source_path(entry['run_meta'])) if entry.get('run_meta') else 'not_applicable',
          'quality_source':entry.get('quality',entry.get('derived_summary','not_applicable')),
          'quality_sha256':sha256(source_path(entry.get('quality',entry.get('derived_summary')))),
          'parser_version':version,'listed_pids':coverage[label]['listed'],
          'incomplete_pid_count':len(coverage[label]['incomplete_pids']),
          'incomplete_pids':','.join(map(str,coverage[label]['incomplete_pids'])) or 'none'})
    return output


def run(manifest_path, out):
    manifest=json.loads(manifest_path.read_text())
    if manifest['schema_version']!=1 or len(manifest['snapshots'])!=6:
        raise ValueError('expected six snapshots and schema_version 1')
    out.mkdir(parents=True,exist_ok=True)
    progress=out/'progress.log'
    def log(message):
        with progress.open('a') as stream:stream.write(now()+' '+message+'\n')
        print(now(),message,flush=True)
    strict, published_rows=strict_identity_set(source_path(manifest['strict_identity_source']))
    published={r['boot']:r for r in read_tsv(source_path(manifest['original_group_summary']))}
    boots={};coverage={}
    for entry in manifest['snapshots']:
        label=entry['label']; log('parse '+label)
        records,cov=(historical_records(entry) if entry['kind']=='historical_smaps' else new_records(entry))
        boots[label]=records;coverage[label]=cov
        log(f'{label}: records={len(records)} incomplete={len(cov["incomplete_pids"])}')
    ledger=derive_partitions(boots,strict)
    six=summarize_six(ledger,strict,published)
    first_part_row=next((r for r in read_tsv(source_path(manifest['published_total_source'])) if r['metric']=='user_Pss_plus_SwapPss'),None)
    if first_part_row is None:
        raise ValueError('published first-part user total row missing')
    first_cols={'GCC1':'GCC1_kB','GCC2':'GCC2_kB','LLVM31':'LLVM3_1_kB','LLVM32':'LLVM3_2_kB',
                'noPIE1':'noPIE1_kB','noPIE2':'noPIE2_kB'}
    history_check=[]
    for row in six:
        prior=dec(first_part_row[first_cols[row['boot']]])
        history_check.append({'boot':row['boot'],'prior_first_part_T_kB':prior,
                              'prior_followup_T_kB':row['published_T_kB'],
                              'unified_T_kB':row['T_kB'],
                              'unified_minus_first_part_kB':row['T_kB']-prior,
                              'unified_minus_followup_kB':row['T_minus_published_kB'],
                              'unified_C_kB':row['C_kB'],
                              'unified_minus_followup_C_kB':row['C_minus_published_kB']})
    images=image_summary(six)
    comparisons=compare_image(images)
    contributions=remaining_contributions(ledger,coverage)
    categories=category_summary(contributions)
    for row in comparisons:
        name=row['comparison']
        rsum=sum((r['observed_delta_kB'] for r in contributions if r['comparison']==name),Decimal(0))
        csum=sum((r['observed_delta_kB'] for r in categories if r['comparison']==name),Decimal(0))
        if rsum!=row['delta_R_kB'] or csum!=row['delta_R_kB']:
            raise ValueError(f'R conservation failed {name}: {rsum}/{csum}/{row["delta_R_kB"]}')
    unknown=[r for r in ledger if r['set']=='R_UNRESOLVED']
    version=sha256(Path(__file__))
    inventory=input_inventory(manifest,coverage,version)
    tsv(out/'inputs.tsv',inventory,list(inventory[0]))
    raw_files=[]
    for entry in manifest['snapshots']:
        if entry['kind']!='image_budget':continue
        state=json.loads(source_path(entry['collection']).read_text())
        collection=source_path(entry['collection']).parent
        for proc in state['processes']:
            path=collection/'raw'/f'process_{proc["pid"]}.stdout'
            raw_files.append({'boot':entry['label'],'pid':proc['pid'],'capture_status':proc['status'],
                              'source':str(path.relative_to(ROOT)),'sha256':sha256(path) if path.exists() else 'MISSING'})
    tsv(out/'new_image_raw_files.tsv',raw_files,['boot','pid','capture_status','source','sha256'])
    fields=['boot','pid','name','exe','identity_key','measurement_status','set','Pss_kB','SwapPss_kB','total_kB','vmas','missing_vmas','source']
    tsv(out/'process_ledger.tsv',ledger,fields)
    tsv(out/'six_snapshots.tsv',six,list(six[0]))
    tsv(out/'historical_value_check.tsv',history_check,list(history_check[0]))
    tsv(out/'image_summary.tsv',images,list(images[0]))
    tsv(out/'comparisons.tsv',comparisons,list(comparisons[0]))
    tsv(out/'remaining_contributions.tsv',contributions,list(contributions[0]))
    tsv(out/'remaining_categories.tsv',categories,list(categories[0]))
    tsv(out/'fixed94_identities.tsv',[{'name':a,'exe':b} for a,b in sorted(strict)],['name','exe'])
    validation={'status':'PASS','fixed_identities':len(strict),'published_strict_rows':len(published_rows),
      'per_boot_T_equals_C_plus_R':{r['boot']:str(r['T_kB']-r['C_kB']-r['R_kB']) for r in six},
      'T_vs_published':{r['boot']:str(r['T_minus_published_kB']) for r in six},
      'C_vs_published':{r['boot']:str(r['C_minus_published_kB']) for r in six},
      'T_vs_first_part':{r['boot']:str(r['unified_minus_first_part_kB']) for r in history_check},
      'delta_conservation':{r['comparison']:str(r['conservation_error_kB']) for r in comparisons},
      'unresolved_identity_measured_kB':str(sum((r['total_kB'] for r in unknown),Decimal(0))),
      'incomplete_processes':{k:v['incomplete_pids'] for k,v in coverage.items()},
      'note':'All totals are measured populations; no unknown memory is imputed.'}
    (out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    log('all conservation checks PASS')
    return validation


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    status='成功'
    try:run(args.manifest,args.out)
    except Exception:
        status='失败'
        raise
    finally:print('已结束',now(),'状态='+status,flush=True)


if __name__=='__main__':main()
