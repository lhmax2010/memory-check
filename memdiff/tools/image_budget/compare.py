#!/usr/bin/env python3
"""Compare one or two boot budgets on a common Pss basis."""
import argparse
import collections
import csv
import datetime
import json
import statistics
import sys
from pathlib import Path


def rows(path):
    if not path.exists(): return []
    with path.open(newline='') as f: return list(csv.DictReader(f, delimiter='\t'))


def write(path, records, fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n',extrasaction='ignore')
        w.writeheader(); w.writerows(records)


def mean_range(values):
    return (statistics.mean(values),max(values)-min(values)) if values else (0,0)


def verdict(delta, baseline_range, new_range, n_baseline, n_new):
    if n_baseline < 2 or n_new < 2:
        return '无波动数据，差值仅供参考'
    return '无显著差异' if abs(delta) <= max(baseline_range,new_range) else '超出两边开机波动'


def load_budget(path):
    data={'dir':path,'summary':json.loads((path/'derived_summary.json').read_text()),
          'metadata':json.loads((path/'budget_metadata.json').read_text()) if (path/'budget_metadata.json').exists() else {},
          'processes':rows(path/'process_budget.tsv'),'files':rows(path/'file_budget.tsv'),
          'elf':rows(path/'elf_metrics.tsv')}
    return data


def aggregate_process(boots):
    # Pair by name and main executable, then sum duplicate instances in each boot.
    result=[]
    for boot in boots:
        grouped=collections.defaultdict(lambda:collections.Counter())
        for p in boot['processes']:
            key=(p['name'],p['exe'])
            for column,value in p.items():
                if column.endswith('_kB') and value not in ('',None):
                    grouped[key][column]+=float(value)
        result.append(grouped)
    return result


def key_status(baseline,new):
    # Strictly paired means present in every supplied boot on both sides.
    b_all=set.intersection(*(set(x) for x in baseline)) if baseline else set()
    n_all=set.intersection(*(set(x) for x in new)) if new else set()
    b_any=set.union(*(set(x) for x in baseline)) if baseline else set()
    n_any=set.union(*(set(x) for x in new)) if new else set()
    return b_all & n_all, b_any - n_any, n_any - b_any


def aggregate_file(boots):
    result=[]
    for boot in boots:
        grouped={}
        for r in boot['files']:
            grouped[r['path']]={k:float(v or 0) for k,v in r.items() if k != 'path'}
        result.append(grouped)
    return result


def main(baseline_dirs,new_dirs,out):
    out.mkdir(parents=True,exist_ok=True)
    log=out/'progress.log'
    def progress(message):
        line=datetime.datetime.now().astimezone().isoformat()+' '+message
        with log.open('a') as f:f.write(line+'\n')
        print(line,flush=True)
    progress('START image budget comparison')
    baseline=[load_budget(p) for p in baseline_dirs]
    new=[load_budget(p) for p in new_dirs]
    bp=aggregate_process(baseline); np=aggregate_process(new)
    paired,bonly,nonly=key_status(bp,np)
    intermittent=(set().union(*(set(x) for x in bp+np)) - paired - bonly - nonly)
    categories=sorted(set().union(*(b['summary']['budget_Pss_kB'] for b in baseline+new)))
    comparison=[]
    for cat in categories:
        bv=[float(b['summary']['budget_Pss_kB'].get(cat,0)) for b in baseline]
        nv=[float(b['summary']['budget_Pss_kB'].get(cat,0)) for b in new]
        bm,br=mean_range(bv); nm,nr=mean_range(nv)
        # Per-process columns use _Pss_kB suffix, except the original code categories.
        col=cat+'_kB' if cat.endswith('_Pss') else cat+'_Pss_kB'
        matched_b=[sum(x[k][col] for k in paired if k in x) for x in bp]
        matched_n=[sum(x[k][col] for k in paired if k in x) for x in np]
        mb,_=mean_range(matched_b); mn,_=mean_range(matched_n)
        comparison.append({'category':cat,'baseline_mean_kB':round(bm,6),'new_mean_kB':round(nm,6),
                           'all_delta_kB':round(nm-bm,6),'matched_delta_kB':round(mn-mb,6),
                           'baseline_range_kB':br,'new_range_kB':nr,
                           'verdict':verdict(nm-bm,br,nr,len(baseline),len(new))})
    fields=list(comparison[0]) if comparison else ['category']
    write(out/'category_comparison.tsv',comparison,fields)
    one_sided=[]
    for side,keys,groups in (('baseline_only',bonly,bp),('new_only',nonly,np)):
        for key in sorted(keys):
            vals=[group[key]['Pss_total_kB'] for group in groups if key in group]
            one_sided.append({'side':side,'name':key[0],'exe':key[1],'present_boots':len(vals),
                              'Pss_mean_kB':round(statistics.mean(vals),6)})
    write(out/'one_sided_processes.tsv',one_sided,['side','name','exe','present_boots','Pss_mean_kB'])
    write(out/'intermittent_processes.tsv',
          ({'name':key[0],'exe':key[1],
            'baseline_present_boots':sum(key in x for x in bp),
            'new_present_boots':sum(key in x for x in np)} for key in sorted(intermittent)),
          ['name','exe','baseline_present_boots','new_present_boots'])
    bf=aggregate_file(baseline); nf=aggregate_file(new)
    common=set.intersection(*(set(x) for x in bf+nf))
    all_files=set.union(*(set(x) for x in bf+nf))
    file_rows=[]
    metrics=['rx_loader_related_Pss_kB','rx_text_Pss_kB','r--_private_dirty_kB','rw-_private_dirty_kB']
    for path in all_files:
        row={'path':path,'population':'common' if path in common else 'single_side'}
        for metric in metrics:
            b=statistics.mean(x.get(path,{}).get(metric,0) for x in bf)
            n=statistics.mean(x.get(path,{}).get(metric,0) for x in nf)
            row[metric+'_baseline']=round(b,6); row[metric+'_new']=round(n,6)
            row[metric+'_delta']=round(n-b,6)
        file_rows.append(row)
    for metric in metrics:
        selected=sorted(file_rows,key=lambda r:-abs(r[metric+'_delta']))[:50]
        write(out/('top50_'+metric+'.tsv'),selected,list(selected[0]) if selected else ['path'])
    elf_rows=[]
    for side,boots in (('baseline',baseline),('new',new)):
        for index,boot in enumerate(boots,1):
            inventory=boot['elf']; mapped=[r for r in inventory if int(r.get('mapped_processes',0))]
            sums=collections.Counter()
            for r in inventory:
                for field in ('defined_WEAK','.dynsym_bytes','.dynstr_bytes','.rel.dyn_bytes','DT_NEEDED_count'):
                    sums[field]+=int(r.get(field,0) or 0)
                sums['PIE_files']+=int(r.get('PIE',0) or 0)
                sums['BIND_NOW_files']+=int(r.get('BIND_NOW',0) or 0)
            elf_rows.append({'side':side,'boot':index,'ELF_count':len(inventory),'mapped_ELF_count':len(mapped),
                             **{k:sums[k] for k in ('defined_WEAK','.dynsym_bytes','.dynstr_bytes','.rel.dyn_bytes','DT_NEEDED_count','PIE_files','BIND_NOW_files')}})
    elf_fields=['side','boot','ELF_count','mapped_ELF_count','defined_WEAK','.dynsym_bytes','.dynstr_bytes','.rel.dyn_bytes','DT_NEEDED_count','PIE_files','BIND_NOW_files']
    write(out/'elf_comparison.tsv',elf_rows,elf_fields)
    elf_delta=[]
    for field in elf_fields[2:]:
        b=statistics.mean(float(r.get(field,0)) for r in elf_rows if r['side']=='baseline')
        n=statistics.mean(float(r.get(field,0)) for r in elf_rows if r['side']=='new')
        elf_delta.append({'metric':field,'baseline_mean':b,'new_mean':n,'delta':n-b})
    write(out/'elf_delta.tsv',elf_delta,['metric','baseline_mean','new_mean','delta'])
    summary={'baseline_boots':len(baseline),'new_boots':len(new),'paired_process_keys':len(paired),
             'baseline_only_process_keys':len(bonly),'new_only_process_keys':len(nonly),
             'intermittent_process_keys':len(intermittent),
             'common_files':len(common),'single_side_files':len(all_files-common),
             'noise_note':'无波动数据，差值仅供参考' if min(len(baseline),len(new))<2 else '差值按两边开机极差判定'}
    (out/'comparison.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    with (out/'comparison.md').open('w') as f:
        f.write('# 镜像内存预算对比\n\n'+summary['noise_note']+'。单位 KiB；新镜像减基线。\n\n')
        f.write(f"严格配对进程键 {len(paired)}；仅基线 {len(bonly)}；仅新镜像 {len(nonly)}。\n\n")
        f.write('| 类别 | 基线 | 新镜像 | 全部差 | 配对差 | 判定 |\n|---|---:|---:|---:|---:|---|\n')
        for r in comparison:
            f.write(f"| {r['category']} | {r['baseline_mean_kB']:.1f} | {r['new_mean_kB']:.1f} | {r['all_delta_kB']:+.1f} | {r['matched_delta_kB']:+.1f} | {r['verdict']} |\n")
        f.write('\n逐文件前 50、单侧进程和 ELF 汇总见同目录 TSV。\n')
    progress('DONE image budget comparison')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--baseline',type=Path,nargs='+',required=True)
    p.add_argument('--new',type=Path,nargs='+',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();status='成功'
    try:main(a.baseline,a.new,a.out)
    except BaseException as e:
        status='失败';print(repr(e),file=sys.stderr,flush=True);raise
    finally:print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态='+status,flush=True)
