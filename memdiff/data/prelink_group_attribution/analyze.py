#!/usr/bin/env python3
"""Offline Pss-to-Pss prelink-group comparison. No board or network access."""
import csv
import gzip
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEMDIFF = HERE.parents[1]
SYS = MEMDIFF / 'data/system_code_page_sections'
SOURCES = json.loads((MEMDIFF / 'data/prelink_overlay_prep/sources.json').read_text())
PROC = re.compile(r'^###\s+(\d+)\s+(\S+)\s+(\S+)$')
MAP = re.compile(r'^[0-9a-f]+-[0-9a-f]+\s+([rwxps-]{4})\s+[0-9a-f]+\s+\S+\s+\d+\s*(.*?)\s*$')
RSS = re.compile(r'^Rss:\s+(\d+)\s+kB$')
PSS = re.compile(r'^Pss:\s+(\d+)\s+kB$')
LOADER = {'dynsym', 'dynstr', 'hash', 'gnu_version', 'rel_dyn', 'rel_plt'}
READELF = Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf')

def log(msg):
    print(datetime.now(timezone.utc).isoformat(timespec='seconds'), msg, flush=True)

def read_tsv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter='\t'))

def write_tsv(name, rows, fields):
    with (HERE / name).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t', lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def gcc_smaps(path):
    """Per process main ELF, all r-x file mappers, max per-VMA Rss and summed Pss."""
    main = {}
    pids = defaultdict(set)
    rss_per_pid = defaultdict(int)
    pss = defaultdict(int)
    pid = None; mapped = None; perms = None; rss_vals = []; pss_vals = []
    def flush():
        if pid is not None and mapped and mapped.startswith('/') and perms == 'r-xp':
            pids[mapped].add(pid)
            rss_per_pid[(mapped,pid)] += sum(rss_vals)
            pss[mapped] += sum(pss_vals)
    with gzip.open(path, 'rt', errors='replace') as stream:
        for raw in stream:
            line = raw.rstrip('\r\n')
            m = PROC.match(line)
            if m:
                flush(); pid = int(m[1]); main[pid] = m[3]; mapped = None; perms = None; rss_vals = []; pss_vals = []
                continue
            m = MAP.match(line)
            if m:
                flush(); perms = m[1]; mapped = m[2].removesuffix(' (deleted)'); rss_vals = []; pss_vals = []
                continue
            m = RSS.match(line)
            if m and mapped is not None: rss_vals.append(int(m[1]))
            m = PSS.match(line)
            if m and mapped is not None: pss_vals.append(int(m[1]))
    flush()
    maxrss = defaultdict(int)
    for (mapped,_),rss in rss_per_pid.items():
        maxrss[mapped] = max(maxrss[mapped],rss)
    return main, pids, maxrss, pss

def current_main(vmas):
    # Lowest-address executable file mapping corresponds to the ELF main image
    # for this collected process set. Flag any paths not in the observed set.
    by_pid = defaultdict(list)
    for row in vmas:
        by_pid[int(row['pid'])].append(row)
    main = {}
    for pid, rows in by_pid.items():
        first = min(rows, key=lambda r: int(r['address'].split('-')[0], 16))
        main[pid] = first['path']
    return main

def quantile(values, q):
    if not values: return 0
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo = int(pos); hi = min(lo + 1, len(values) - 1)
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)

def main():
    log('读取 ELF 标记、节表与可信共同文件')
    files = [r for r in read_tsv(SYS/'file_residency.tsv') if r['population']=='common' and r['eligible']=='True']
    elf = {(r['image'],r['path']):r for r in read_tsv(SYS/'elf_summary.tsv')}
    ten = sorted(r['path'] for r in elf.values() if r['image']=='GCC' and r['GNU_LIBLIST']=='True')
    if len(ten)!=10: raise ValueError(f'GNU_LIBLIST executable count {len(ten)} != 10')
    ten_set = set(ten)
    static = defaultdict(int)
    for r in read_tsv(SYS/'elf_sections.tsv'):
        if r['group'] in LOADER and r['section_type']!='NOBITS':
            static[(r['image'],r['path'])] += int(r['size_bytes'])
    role = {r['path']:r['role'] for r in read_tsv(MEMDIFF/'data/gcc_baseline/elf/elf_stats.tsv')}
    vmas = read_tsv(SYS/'vmas.tsv')
    current = current_main(vmas)
    llvm_pids = defaultdict(set); llvm_pss = defaultdict(int); llvm_maxrss = defaultdict(int)
    llvm_rss_per_pid = defaultdict(int)
    for r in vmas:
        path = r['path']; pid = int(r['pid'])
        llvm_pids[path].add(pid)
        llvm_pss[path] += int(r['Pss_kB'])
        llvm_rss_per_pid[(path,pid)] += int(r['Rss_kB'])
    for (path,_),rss in llvm_rss_per_pid.items():
        llvm_maxrss[path] = max(llvm_maxrss[path],rss)
    log(f'当前 LLVM {len(current)} 个进程、{len(llvm_pids)} 个 r-x 路径')
    gcc = {}
    for boot in ('GCC1','GCC2'):
        log(f'流式读取 {boot} smaps')
        gcc[boot] = gcc_smaps(MEMDIFF / SOURCES[boot])
        log(f'{boot}: {len(gcc[boot][0])} 个进程、{len(gcc[boot][1])} 个 r-x 路径')
    process_rows=[]
    for boot,main_map in [('GCC1',gcc['GCC1'][0]),('GCC2',gcc['GCC2'][0]),('LLVM',current)]:
        for pid,path in sorted(main_map.items()):
            process_rows.append(dict(image_boot=boot,pid=pid,main_executable=path,
                                     in_gnu_liblist_ten=int(path in ten_set),
                                     identification='smaps ### PID comm exe header' if boot!='LLVM' else 'lowest-address r-xp file VMA in saved maps'))
    write_tsv('process_main.tsv',process_rows,list(process_rows[0]))
    per = []
    for index,r in enumerate(files,1):
        path = r['path']
        cur_pids = llvm_pids[path]
        other = []
        for boot in ('GCC1','GCC2'):
            main_g,pid_g,_,_ = gcc[boot]
            other += [(boot,p,main_g.get(p,'')) for p in pid_g[path] if main_g.get(p,'') not in ten_set]
        other += [('LLVM',p,current.get(p,'')) for p in cur_pids if current.get(p,'') not in ten_set]
        pre = elf[('GCC',path)]['prelink_marker_any']=='True'
        if path in ten_set: group='甲'
        elif role.get(path)=='+so':
            group=('乙' if not other else '丙') if pre else '丁'
        else: group='戊'
        unique=float(r['LLVM_unique_rx_Rss_kB'])
        resident=float(r['LLVM_loader_resident_kB'])
        pss=llvm_pss[path]
        gcc1=int(r['GCC1_rx_Pss_sum_kB']); gcc2=int(r['GCC2_rx_Pss_sum_kB'])
        if gcc1!=gcc['GCC1'][3][path] or gcc2!=gcc['GCC2'][3][path]:
            raise ValueError(f'GCC source Pss mismatch for {path}')
        gccmean=(gcc1+gcc2)/2
        frac=resident/unique if unique else 0
        loader_pss=pss*frac
        gcc_static=static[('GCC',path)]/1024
        llvm_static=static[('LLVM',path)]/1024
        lower=loader_pss-min(gccmean,gcc_static)
        # A conservative alternative bounded by the observed Pss-vs-unique gap.
        lower_conservative=max(0,pss-(unique-resident))-min(gccmean,gcc_static)
        gcchs=[gcc[b][2].get(path,0) for b in ('GCC1','GCC2')]
        gcc_cond=[int(x<gcc_static) if path in gcc[b][1] else '' for b,x in zip(('GCC1','GCC2'),gcchs)]
        ll_cond=int(llvm_maxrss[path]<llvm_static)
        gcc_file=MEMDIFF/'data/gcc_baseline/elf/files'/path.lstrip('/')
        llvm_file=SYS/'elf'/path.lstrip('/')
        same=bool(gcc_file.is_file() and llvm_file.is_file() and sha(gcc_file)==sha(llvm_file))
        per.append(dict(path=path,group=group,same_sha256=int(same),gcc_prelink_marker=int(pre),gcc_role=role.get(path,''),
            llvm_mappers=len(cur_pids),gcc1_mappers=len(gcc['GCC1'][1][path]),gcc2_mappers=len(gcc['GCC2'][1][path]),
            outside_ten_mappers=len(other),outside_ten_examples=';'.join(f'{b}:{p}:{exe}' for b,p,exe in other[:5]),
            llvm_unique_rx_kB=unique,llvm_pss_sum_kB=pss,rounding_gap_kB=unique-pss,
            gcc1_pss_sum_kB=gcc1,gcc2_pss_sum_kB=gcc2,gcc_mean_pss_kB=gccmean,pss_delta_kB=pss-gccmean,
            llvm_loader_unique_kB=resident,llvm_loader_pss_est_kB=loader_pss,
            gcc_loader_static_kB=gcc_static,llvm_loader_static_kB=llvm_static,
            loader_growth_lower_est_kB=lower,loader_growth_lower_conservative_kB=lower_conservative,
            gcc1_max_rx_rss_kB=gcchs[0],gcc2_max_rx_rss_kB=gcchs[1],llvm_max_rx_rss_kB=llvm_maxrss[path],
            gcc1_maxrss_lt_static=gcc_cond[0],gcc2_maxrss_lt_static=gcc_cond[1],llvm_maxrss_lt_static=ll_cond))
        if index%200==0: log(f'已分析 {index}/{len(files)} 文件')
    write_tsv('per_file.tsv',per,list(per[0]))
    log('汇总各组与映射进程数分档')
    groups=[]
    for group in '甲乙丙丁戊己':
        rows=[r for r in per if (r['same_sha256'] if group=='己' else r['group']==group)]
        def total(key): return sum(float(r[key]) for r in rows)
        count=len(rows)
        g=dict(group=group,files=count,llvm_pss_sum_kB=total('llvm_pss_sum_kB'),
               gcc1_pss_sum_kB=total('gcc1_pss_sum_kB'),gcc2_pss_sum_kB=total('gcc2_pss_sum_kB'),
               gcc_mean_pss_kB=total('gcc_mean_pss_kB'),pss_delta_kB=total('pss_delta_kB'),
               llvm_loader_unique_kB=total('llvm_loader_unique_kB'),llvm_loader_pss_est_kB=total('llvm_loader_pss_est_kB'),
               gcc_loader_static_kB=total('gcc_loader_static_kB'),llvm_loader_static_kB=total('llvm_loader_static_kB'),
               loader_growth_lower_est_kB=total('loader_growth_lower_est_kB'),
               loader_growth_lower_conservative_kB=total('loader_growth_lower_conservative_kB'))
        for boot in ('gcc1','gcc2','llvm'):
            n=sum(r[f'{boot}_maxrss_lt_static']==1 for r in rows)
            denom=sum(r[f'{boot}_maxrss_lt_static']!='' for r in rows)
            g[f'{boot}_maxrss_lt_static_files']=n
            g[f'{boot}_maxrss_lt_static_ratio']=n/denom if denom else 0
            g[f'{boot}_measured_files']=denom
        groups.append(g)
    write_tsv('group_summary.tsv',groups,list(groups[0]))
    bins=[]
    for label,fn in [('1',lambda n:n==1),('2-9',lambda n:2<=n<=9),('10-49',lambda n:10<=n<=49),('>=50',lambda n:n>=50)]:
        rows=[r for r in per if fn(r['llvm_mappers'])]
        bins.append(dict(mappers_bin=label,files=len(rows),llvm_unique_rx_kB=sum(r['llvm_unique_rx_kB'] for r in rows),
            llvm_pss_sum_kB=sum(r['llvm_pss_sum_kB'] for r in rows),unique_minus_pss_kB=sum(r['rounding_gap_kB'] for r in rows)))
    write_tsv('rounding_by_mapper_count.tsv',bins,list(bins[0]))
    log('核对 10 个当前 LLVM ELF 类型与 PIE 标志')
    checked=[]
    for path in ten:
        f=SYS/'elf'/path.lstrip('/')
        if not f.is_file(): checked.append(dict(path=path,status='missing',elf_type='',pie='')); continue
        h=subprocess.run([str(READELF),'-hW',str(f)],capture_output=True,text=True)
        d=subprocess.run([str(READELF),'-dW',str(f)],capture_output=True,text=True)
        elf_type=next((x.split('Type:',1)[1].strip().split()[0] for x in h.stdout.splitlines() if 'Type:' in x),'')
        pie=('PIE' in d.stdout)
        checked.append(dict(path=path,status='OK' if h.returncode==0 and d.returncode==0 else f'readelf_rc={h.returncode},{d.returncode}',elf_type=elf_type,pie=int(pie)))
    write_tsv('gnu_liblist_executables.tsv',checked,list(checked[0]))
    static14=[]
    for r in read_tsv(MEMDIFF/'data/static/process_comparison_by_executable.tsv'):
        if r['group']=='gcc_nonpie': static14.append(r['executable'])
    weekly=[]
    text=(MEMDIFF/'reports/weekly_data_table.md').read_text().splitlines()
    for line_no,line in enumerate(text,1):
        if line.startswith('| `') and 'PSS 差：第一轮' not in line and 'PSS' not in line and ' | ' in line and 65<=line_no<=85:
            weekly.append(line.split('`')[1])
    if len(weekly)!=15: raise ValueError(f'weekly 15 list parsed as {len(weekly)}')
    all10=set(ten)
    comparison=dict(ten=ten,static14=static14,weekly15=weekly,
       ten_intersect_static14=sorted(all10&set(static14)),ten_only_vs_static14=sorted(all10-set(static14)),static14_only=sorted(set(static14)-all10),
       ten_intersect_weekly15=sorted(all10&set(weekly)),ten_only_vs_weekly15=sorted(all10-set(weekly)),weekly15_only=sorted(set(weekly)-all10))
    (HERE/'program_list_comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+'\n')
    same=[r['pss_delta_kB'] for r in per if r['same_sha256']]
    result=dict(eligible_files=len(per),llvm_pss_sum_kB=sum(r['llvm_pss_sum_kB'] for r in per),
        gcc1_pss_sum_kB=sum(r['gcc1_pss_sum_kB'] for r in per),gcc2_pss_sum_kB=sum(r['gcc2_pss_sum_kB'] for r in per),
        gcc_mean_pss_kB=sum(r['gcc_mean_pss_kB'] for r in per),pss_delta_kB=sum(r['pss_delta_kB'] for r in per),
        unique_minus_pss_kB=sum(r['rounding_gap_kB'] for r in per),
        group_A_B_lower_est_kB=sum(g['loader_growth_lower_est_kB'] for g in groups[:2]),
        group_A_B_lower_conservative_kB=sum(g['loader_growth_lower_conservative_kB'] for g in groups[:2]),
        group_A_B_upper_kB=sum(g['llvm_loader_pss_est_kB'] for g in groups[:2]),
        noise_total_delta_kB=sum(same),noise_median_file_delta_kB=quantile(same,.5),noise_p90_file_delta_kB=quantile(same,.9),
        current_main_missing=0,readelf=str(READELF),sources=SOURCES)
    (HERE/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    log(f"完成：可信文件 {len(per)}，Pss 差 {result['pss_delta_kB']} KiB")

if __name__=='__main__':
    status='成功'
    try: main()
    except BaseException:
        status='失败'
        raise
    finally:
        print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+status,flush=True)
