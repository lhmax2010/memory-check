#!/usr/bin/env python3
"""Cross-check the new readelf inventory against the prior independent ELF inventory."""
import csv,datetime,json
from pathlib import Path
O=Path(__file__).resolve().parent
S=O.parent/'system_code_page_sections'
def rows(path):
 with path.open() as f:yield from csv.DictReader(f,delimiter='\t')
def main():
 old={r['path']:r for r in rows(S/'elf_summary.tsv') if r['image']=='LLVM'}
 new={r['path']:r for r in rows(O/'elf_metrics.tsv')}
 keys=['defined_GLOBAL','defined_WEAK','undefined','.dynsym_bytes','.dynstr_bytes','.rel.plt_bytes']
 mismatches={k:[p for p in new if p in old and new[p][k]!=old[p][k]] for k in keys}
 budget=json.loads((O/'derived_summary.json').read_text())
 model=json.loads((O/'relocation_summary.json').read_text())
 psum=sum(budget['budget_Pss_kB'].values())
 checks={'same_ELF_path_set':set(old)==set(new),'readelf_errors_zero':model['readelf_errors']==0,
         'Pss_categories_sum':abs(psum-budget['Pss_total_kB'])<.01,
         'independent_symbol_and_section_metrics_equal':all(not v for v in mismatches.values()),
         'relocation_model_error_disclosed':model['absolute_percentage_error_vs_observed']>.2}
 result={'checks':checks,'old_ELF_count':len(old),'new_ELF_count':len(new),
         'mismatch_counts':{k:len(v) for k,v in mismatches.items()},
         'mismatch_examples':{k:v[:10] for k,v in mismatches.items() if v},
         'Pss_category_sum_kB':psum,'Pss_total_kB':budget['Pss_total_kB']}
 (O/'qa.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 if not all(checks.values()):raise RuntimeError(result)
 print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态=成功',flush=True)
if __name__=='__main__':
 status='失败'
 try:main();status='成功'
 finally:
  if status!='成功':print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态=失败',flush=True)
