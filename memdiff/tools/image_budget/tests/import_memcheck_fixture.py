#!/usr/bin/env python3
"""Validation-only adapter: historical memcheck smaps lacks pagemap/ELF inventories."""
import argparse
import collections
import csv
import gzip
import json
import re
from pathlib import Path

HEADER=re.compile(r'^###\s+(\d+)\s+(\S+)\s+(\S+)')
MAP=re.compile(r'^[0-9a-f]+-[0-9a-f]+\s+([rwxps-]{4})\s+[0-9a-f]+\s+\S+\s+\d+\s*(.*?)\s*$')
METRIC=re.compile(r'^(Pss|Pss_Dirty|SwapPss|Private_Dirty):\s+(\d+)\s+kB$')


def write(path,records,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n',extrasaction='ignore')
        w.writeheader();w.writerows(records)


def main(source,out):
    out.mkdir(parents=True,exist_ok=True)
    procs=collections.defaultdict(lambda:collections.Counter())
    files=collections.defaultdict(lambda:collections.Counter())
    categories=collections.Counter()
    pid=None;name='';exe='';path='';perms='';metrics={}
    def flush():
        if pid is None or not perms:return
        pss=metrics.get('Pss',0);dirty=metrics.get('Private_Dirty',0);pd=metrics.get('Pss_Dirty',dirty)
        sw=metrics.get('SwapPss',0)
        record=procs[(pid,name,exe)]
        record['Pss_total_kB']+=pss;record['SwapPss_kB']+=sw
        if path.startswith('/') and perms.startswith('r-x'):
            cat='code_code_other';record[cat+'_Pss_kB']+=pss;categories[cat]+=pss
            files[path]['rx_code_other_Pss_kB']+=pss
        elif path.startswith('/') and perms.startswith(('r--','rw-')):
            kind='r--' if perms.startswith('r--') else 'rw-'
            d=min(pss,dirty);sd=max(0,min(pss,pd)-d)
            for part,value in (('private_dirty',d),('shared_dirty_Pss',sd),('clean',pss-d-sd)):
                key=f'file_{kind}_{part}';categories[key]+=value
                record[key+'_kB' if key.endswith('_Pss') else key+'_Pss_kB']+=value
            files[path][kind+'_private_dirty_kB']+=dirty
        elif path.startswith('/'):
            categories['file_other']+=pss;record['file_other_Pss_kB']+=pss
        else:
            cat='anon_heap' if path=='[heap]' else 'anon_stack' if path.startswith('[stack') else 'anon_unlabelled' if not path or path.startswith('[anon:') else 'anon_other_named'
            categories[cat]+=pss;record[cat+'_Pss_kB']+=pss
    with gzip.open(source,'rt',errors='replace') as f:
        for line in f:
            m=HEADER.match(line)
            if m:
                flush();pid=int(m[1]);name=m[2];exe=m[3];path='';perms='';metrics={};continue
            m=MAP.match(line)
            if m:
                flush();perms=m[1];path=m[2].removesuffix(' (deleted)');metrics={};continue
            m=METRIC.match(line)
            if m:metrics[m[1]]=int(m[2])
    flush()
    fields=['pid','name','exe','Pss_total_kB','SwapPss_kB']+sorted({key for c in procs.values() for key in c if key not in ('Pss_total_kB','SwapPss_kB')})
    write(out/'process_budget.tsv',({'pid':pid,'name':name,'exe':exe,**c} for (pid,name,exe),c in procs.items()),fields)
    ffields=['path','rx_code_other_Pss_kB','r--_private_dirty_kB','rw-_private_dirty_kB']
    write(out/'file_budget.tsv',({'path':p,**{k:c[k] for k in ffields[1:]}} for p,c in files.items()),ffields)
    (out/'derived_summary.json').write_text(json.dumps({'budget_Pss_kB':dict(categories),'Pss_total_kB':sum(c['Pss_total_kB'] for c in procs.values()),
           'SwapPss_total_kB':sum(c['SwapPss_kB'] for c in procs.values())},indent=2)+'\n')
    (out/'budget_metadata.json').write_text(json.dumps({'boot_count':1,'source':'historical_memcheck_smaps',
        'limitations':'no pagemap, so r-x Pss is code_other; no ELF metrics; comparison is a parser validation only'},indent=2)+'\n')
    write(out/'elf_metrics.tsv',[],['path','defined_WEAK','.dynsym_bytes','.dynstr_bytes','.rel.dyn_bytes','DT_NEEDED_count','PIE','BIND_NOW','mapped_processes'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();main(a.input,a.out)
