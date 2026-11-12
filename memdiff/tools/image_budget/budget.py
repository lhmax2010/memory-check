#!/usr/bin/env python3
"""Build a reusable one-boot image budget from a saved image_budget collection."""
import argparse
import collections
import csv
import datetime
import gzip
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
READELF = Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf')
SECTION = re.compile(r'^\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+\S+\s+([A-Z]*)')
LOADER = {'.dynsym', '.dynstr', '.gnu.hash', '.hash', '.rel.dyn', '.rel.plt'}


def load(name):
    spec = importlib.util.spec_from_file_location('image_budget_' + name, HERE / 'engine' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tsv(path, rows, fields):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fields, delimiter='\t', lineterminator='\n', extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def read(path):
    with path.open(newline='') as f:
        yield from csv.DictReader(f, delimiter='\t')


def allocate_page(page_start, page_size, sections):
    """Allocate one present file page by byte overlap; NOBITS occupies no file bytes."""
    amounts = collections.defaultdict(float)
    used = 0
    for sec in sections:
        if sec['kind'] == 'NOBITS':
            continue
        overlap = max(0, min(page_start + page_size, sec['offset'] + sec['size']) - max(page_start, sec['offset']))
        if overlap:
            amounts[sec['name']] += overlap / 1024
            used += overlap
    if used > page_size:
        raise ValueError('overlapping ELF sections')
    if used < page_size:
        amounts['<headers/padding/unassigned>'] += (page_size-used)/1024
    return amounts


def prepare(source, log):
    state = json.loads((source / 'collection.json').read_text())
    if state.get('status') != 'DONE' or not state.get('root_restored'):
        raise RuntimeError('collection incomplete or root restoration unconfirmed')
    if not (source / 'unique_pages.tsv.gz').exists():
        mod = load('parse_pages'); mod.HERE = source; mod.main()
    if (source / 'section_residency.tsv').exists() and (source / 'file_residency.tsv').exists() and (source / 'dynsym_symbols.tsv.gz').exists():
        log('reuse verified section residency and dynsym inventory')
        return
    sections = collections.defaultdict(list)
    all_elf = sorted(p for p in (source/'elf').rglob('*') if p.is_file() and not p.is_symlink())
    with gzip.open(source/'dynsym_symbols.tsv.gz', 'wt', newline='') as stream:
        w = csv.DictWriter(stream, ['image','path','bind','ndx','name','visibility'], delimiter='\t', lineterminator='\n')
        w.writeheader()
        for index, file in enumerate(all_elf, 1):
            if file.open('rb').read(4) != b'\x7fELF':
                continue
            path = '/' + str(file.relative_to(source/'elf'))
            result = subprocess.run([str(READELF), '-SW', '--dyn-syms', '-W', str(file)],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, errors='replace', timeout=180)
            if result.returncode:
                raise RuntimeError(f'readelf {path}: {result.stderr}')
            in_dynsym = False
            for line in result.stdout.splitlines():
                match = SECTION.match(line)
                if match:
                    sections[path].append({'name':match[1], 'kind':match[2], 'offset':int(match[4],16), 'size':int(match[5],16)})
                if line.startswith("Symbol table '.dynsym'"):
                    in_dynsym = True; continue
                if line.startswith('Symbol table '):
                    in_dynsym = False
                if in_dynsym:
                    parts = line.split()
                    if len(parts) >= 8 and parts[0].endswith(':') and parts[0][:-1].isdigit():
                        w.writerow({'image':'LLVM','path':path,'bind':parts[4], 'ndx':parts[6],
                                    'name':parts[7], 'visibility':parts[5]})
            if index % 100 == 0:
                log(f'ELF inventory {index}/{len(all_elf)}')
    page_size = state['page_size']
    allocated = collections.defaultdict(float)
    counts = collections.Counter()
    excluded = {r['path']:r['dedup_exclusion'] for r in read(source/'files_from_pages.tsv')
                if r['dedup_exclusion']}
    tsv(source/'residency_exclusions.tsv',
        ({'path':p,'reason':reason} for p,reason in sorted(excluded.items())),['path','reason'])
    with gzip.open(source/'unique_pages.tsv.gz', 'rt') as f:
        for index, row in enumerate(csv.DictReader(f, delimiter='\t'), 1):
            path = row['path']; offset = int(row['file_offset_bytes'])
            if path in excluded:
                continue
            for name, value in allocate_page(offset, page_size, sections[path]).items():
                allocated[(path,name)] += value
            counts[path] += 1
            if index % 100000 == 0:
                log(f'allocated {index} unique pages')
    tsv(source/'section_residency.tsv',
        ({'path':p,'section':s,'group':'loader' if s in LOADER or s.startswith('.gnu.version') else 'other',
          'resident_kB':round(v,6)} for (p,s),v in sorted(allocated.items())),
        ['path','section','group','resident_kB'])
    tsv(source/'file_residency.tsv',
        ({'path':p,'LLVM_unique_rx_Rss_kB':n*page_size/1024} for p,n in counts.items()),
        ['path','LLVM_unique_rx_Rss_kB'])


def process_identity(source, pid):
    raw = source/'raw'/f'process_{pid}.stdout'
    name = ''; exe = ''; cmdline = ''
    if not raw.exists():
        return name, exe, cmdline
    section = ''
    with raw.open(errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            if line in ('__STATUS_BEGIN__','__CMDLINE_BEGIN__','__EXE_BEGIN__'):
                section = line; continue
            if line in ('__STATUS_END__','__CMDLINE_END__','__EXE_END__'):
                section = ''; continue
            if section == '__STATUS_BEGIN__' and line.startswith('Name:'):
                name = line.split(':',1)[1].strip()
            if section == '__CMDLINE_BEGIN__' and line:
                cmdline = line
            if section == '__EXE_BEGIN__' and line:
                exe = line
    return name, exe, cmdline


def output_details(source, out, state):
    per_file = collections.defaultdict(lambda:collections.Counter())
    per_process = collections.defaultdict(lambda:collections.Counter())
    section = collections.defaultdict(lambda:collections.Counter())
    classify_section = load('compute').section_class
    for row in read(source/'section_residency.tsv'):
        section[row['path']][classify_section(row['section'])] += float(row['resident_kB'])
    for row in read(out/'vmas_all.tsv'):
        pid = int(row['pid']); path = row['path']; perms = row['perms']; pss = int(row['Pss_kB'])
        if path.startswith('/') and perms.startswith('r-x'):
            den = sum(section[path].values())
            for group in ('loader_related','text','rodata','arm_unwind','plt','code_other'):
                value = pss * section[path][group]/den if den else (pss if group == 'code_other' else 0)
                per_file[path]['rx_'+group+'_Pss_kB'] += value
                per_process[pid]['code_'+group+'_Pss_kB'] += value
        elif path.startswith('/') and perms.startswith(('r--','rw-')):
            key = 'r--' if perms.startswith('r--') else 'rw-'
            dirty = int(row['Private_Dirty_kB'])
            private_pss = min(pss,dirty)
            shared_pss = max(0,min(pss,int(row['Pss_Dirty_kB']))-private_pss)
            per_file[path][key+'_private_dirty_kB'] += dirty
            per_process[pid]['file_'+key+'_private_dirty_Pss_kB'] += private_pss
            per_process[pid]['file_'+key+'_shared_dirty_Pss_kB'] += shared_pss
            per_process[pid]['file_'+key+'_clean_Pss_kB'] += pss-private_pss-shared_pss
        else:
            if path == '[heap]': cat='anon_heap'
            elif path.startswith('[stack'): cat='anon_stack'
            elif not path or path.startswith('[anon:'): cat='anon_unlabelled'
            elif path.startswith('/'): cat='file_other'
            else: cat='anon_other_named'
            per_process[pid][cat+'_Pss_kB'] += pss
        per_process[pid]['Pss_total_kB'] += pss
        per_process[pid]['SwapPss_kB'] += int(row['SwapPss_kB'])
    file_fields = ['path','rx_loader_related_Pss_kB','rx_text_Pss_kB','rx_rodata_Pss_kB',
                   'rx_arm_unwind_Pss_kB','rx_plt_Pss_kB','rx_code_other_Pss_kB',
                   'r--_private_dirty_kB','rw-_private_dirty_kB']
    tsv(out/'file_budget.tsv', ({'path':p,**{k:round(v[k],6) for k in file_fields[1:]}} for p,v in sorted(per_file.items())), file_fields)
    process_fields = ['pid','name','exe','cmdline','Pss_total_kB','SwapPss_kB'] + sorted({k for v in per_process.values() for k in v if k not in ('Pss_total_kB','SwapPss_kB')})
    exe_fallback = {}
    for row in read(out/'vmas_all.tsv'):
        pid = int(row['pid'])
        if pid not in exe_fallback and row['perms'].startswith('r-x') and row['path'].startswith('/'):
            exe_fallback[pid] = row['path']
    def p_rows():
        for pid, values in sorted(per_process.items()):
            name,exe,cmdline = process_identity(source,pid)
            if not exe:
                # Historical 11-11 collection omitted /proc/pid/exe; use the first r-x file mapping as a labelled fallback.
                exe = exe_fallback.get(pid,'')
            if not name:
                name = Path(exe).name if exe else f'pid:{pid}'
            yield {'pid':pid,'name':name,'exe':exe,'cmdline':cmdline,**{k:round(values[k],6) for k in process_fields[4:]}}
    tsv(out/'process_budget.tsv', p_rows(), process_fields)
    mem = source/'raw/snapshot_meminfo.stdout'
    page_tables = None
    if mem.exists():
        match = re.search(r'^PageTables:\s+(\d+)\s+kB',mem.read_text(),re.MULTILINE)
        if match: page_tables = int(match[1])
    (out/'budget_metadata.json').write_text(json.dumps({'build_id':state.get('build_id',''),
        'boot_count':1,'capture_reason':state.get('capture_reason','legacy_snapshot'),
        'capture_uptime_s':state.get('capture_uptime_s'), 'PageTables_kB':page_tables,
        'process_identity_source':'proc_status_exe' if state.get('stability_samples') else 'first_rx_mapping_fallback'},indent=2)+'\n')


def main(source, out):
    out.mkdir(parents=True, exist_ok=True)
    log_file = out/'progress.log'
    def log(msg):
        value = datetime.datetime.now().astimezone().isoformat()+' '+msg
        with log_file.open('a') as f: f.write(value+'\n')
        print(value,flush=True)
    log('START image budget')
    prepare(source,log)
    state = json.loads((source/'collection.json').read_text())
    compute = load('compute'); compute.OUT = out; compute.SRC = source; compute.LOG = log_file
    compute.main()
    weak = load('weak_symbols'); weak.OUT = out; weak.SRC = source
    weak.main()
    relro = load('classify_relro'); relro.O = out; relro.ROOT = source/'elf'
    relro.main()
    derive = load('derive'); derive.O = out; derive.S = source
    derive.main()
    output_details(source,out,state)
    pulls=collections.Counter(p.get('status','unknown') for p in state.get('pulled',[]))
    missing=[p.get('path','') for p in state.get('pulled',[]) if p.get('status') in ('pull_failed','hash_mismatch_or_unavailable')]
    (out/'collection_quality.json').write_text(json.dumps({'pull_status_counts':dict(pulls),
        'missing_or_unverified_elf_paths':missing,'incomplete_processes':sum(p.get('status')!='complete' for p in state['processes'])},indent=2)+'\n')
    report = json.loads((out/'derived_summary.json').read_text())
    relocation = json.loads((out/'relocation_summary.json').read_text())
    with (out/'budget.md').open('w') as f:
        f.write('# 镜像内存预算\n\n')
        f.write(f"BUILD_ID: `{report['image_BUILD_ID']}`；采集日期：{report['snapshot_date']}；单次开机。单位 KiB。\n\n")
        f.write(f"用户进程 Pss {report['Pss_total_kB']}；SwapPss {report['SwapPss_total_kB']}；")
        f.write(f"PageTables {report['PageTables_same_snapshot_kB']}。\n\n")
        if missing:
            f.write(f"注意：{len(missing)} 个映射路径拉取失败或 SHA256 未核对，静态 ELF 细分可能不完整；见 `collection_quality.json`。\n\n")
        f.write('| 互斥 Pss 类别 | KiB | 占 Pss |\n|---|---:|---:|\n')
        for key,value in report['budget_Pss_kB'].items():
            f.write(f"| {key} | {value:.3f} | {100*value/report['Pss_total_kB']:.2f}% |\n")
        f.write('\n重定位、ELF 指标和驻留前 50 分别见 `relocation_summary.json`、`elf_metrics.tsv`、`code_top50_pages.tsv`。')
        f.write(f"动态重定位数：{relocation['dynamic_relocations_parsed']}。逐文件 Pss 见 `file_budget.tsv`。\n")
    log('DONE image budget')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    status='成功'
    try: main(args.input.resolve(),args.out.resolve())
    except BaseException as e:
        status='失败'; print(repr(e),file=sys.stderr,flush=True); raise
    finally: print('已结束',datetime.datetime.now().astimezone().isoformat(),'状态='+status,flush=True)
