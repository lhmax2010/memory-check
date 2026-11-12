#!/usr/bin/env python3
"""Compare a fresh tool run to the published 11-11 budget, excluding PageTables."""
import argparse
import json
from pathlib import Path

FILES=['smaps_budget.json','code_budget.json','relocation_summary.json',
       'relro_classification_summary.json','symbol_estimates.json']
NUMERIC_DERIVED=['measured_user_processes','smaps_processes_including_kernel_threads',
 'exited_or_incomplete_processes','Pss_total_kB','SwapPss_total_kB','Pss_plus_SwapPss_kB',
 'budget_Pss_kB','VMA_distribution','mapped_libraries_distribution','section_Pss_kB',
 'relocation_page_bounds','BIND_NOW_all_ELF','BIND_NOW_mapped_ELF',
 'BIND_NOW_mapped_ELF_with_JUMP_SLOT','WEAK_export_categories']


def main(published,actual,out):
    result={'files':{},'derived_fields':{},'mismatches':[]}
    for name in FILES:
        a=json.loads((actual/name).read_text());b=json.loads((published/name).read_text())
        result['files'][name]='一致' if a==b else '不一致'
        if a!=b:
            result['mismatches'].append(name)
    a=json.loads((actual/'derived_summary.json').read_text())
    b=json.loads((published/'derived_summary.json').read_text())
    for key in NUMERIC_DERIVED:
        result['derived_fields'][key]='一致' if a.get(key)==b.get(key) else '不一致'
        if a.get(key)!=b.get(key):result['mismatches'].append('derived_summary.json:'+key)
    result['checked_count']=len(FILES)+len(NUMERIC_DERIVED)
    result['status']='PASS' if not result['mismatches'] else 'FAIL'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(result['status'],result['checked_count'],'items',result['mismatches'])
    return not result['mismatches']


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--published',type=Path,required=True)
    p.add_argument('--actual',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();raise SystemExit(0 if main(a.published,a.actual,a.out) else 1)
