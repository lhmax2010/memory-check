#!/usr/bin/env python3
"""Resolve saved GCC ELF DT_NEEDED edges without reading a board or VD network."""
import csv
import json
import re
import subprocess
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEMDIFF = HERE.parents[1]
FILES = MEMDIFF / 'data/gcc_baseline/elf/files'
READELF = '/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf'
LD_DIRS = '/lib:/usr/lib:/prd/usr/lib:/usr/lib/was-api:/usr/lib/ecore_imf/modules/isf/v-1.13:/usr/lib/gstreamer-1.0:/usr/lib/pulseaudio:/usr/lib/hal'.split(':')
CONF_DIRS = '/opt/usr/apps/com.samsung.tv.slive-daemon/lib:/lib:/usr/lib:/prd/usr/lib:/usr/lib/was-api:/usr/lib/ecore_imf/modules/isf/v-1.13:/usr/lib/gstreamer-1.0:/usr/lib/pulseaudio'.split(':')
TARGETS = '''/usr/bin/tvs-daemon /usr/bin/TIFSDaemon /usr/bin/app-boot-manager /usr/apps/boot-helper-dyboost-tv/bin/boot-helper-dyboost-tv /usr/bin/fastinit /usr/bin/avocd /usr/bin/fastlogo /usr/bin/amd /usr/bin/fastvideo /usr/apps/org.tizen.tv-viewer/bin/tv-viewer /usr/bin/rscmgr-service /usr/bin/pulseaudio /usr/apps/org.tizen.btapp/bin/btapp /usr/bin/hdmicec-service /usr/apps/org.tizen.acm-service/bin/acm-service /usr/bin/launchpad-loader /usr/bin/launchpad-process-pool /usr/bin/app_launcher /usr/apps/org.tizen.welcome-mode/bin/welcome-mode'''.split()
TAG = re.compile(r'\((NEEDED|SONAME|RPATH|RUNPATH)\).*?\[([^]]*)\]')

def log(msg): print(datetime.now(timezone.utc).isoformat(timespec='seconds'),msg,flush=True)
def write(name,rows,fields):
    with (HERE/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    paths=sorted('/'+str(p.relative_to(FILES)) for p in FILES.rglob('*') if p.is_file())
    dynamic={}; raw=[]; errors=[]
    log(f'scan {len(paths)} saved GCC ELF copies')
    for i,path in enumerate(paths,1):
        r=subprocess.run([READELF,'-dW',str(FILES/path.lstrip('/'))],capture_output=True,text=True)
        tags=defaultdict(list)
        for line in r.stdout.splitlines():
            m=TAG.search(line)
            if m:tags[m.group(1)].append(m.group(2))
        dynamic[path]=dict(needed=tags['NEEDED'],soname=tags['SONAME'][0] if tags['SONAME'] else '',rpath=tags['RPATH'],runpath=tags['RUNPATH'])
        raw.append(dict(path=path,soname=dynamic[path]['soname'],needed_count=len(tags['NEEDED']),needed=';'.join(tags['NEEDED']),rpath=';'.join(tags['RPATH']),runpath=';'.join(tags['RUNPATH']),readelf_rc=r.returncode))
        if r.returncode:errors.append(dict(path=path,rc=r.returncode,stderr=r.stderr.strip()))
        if i%100==0:log(f'scanned {i}/{len(paths)}')
    write('elf_dynamic.tsv',raw,list(raw[0]))
    write('readelf_errors.tsv',errors,['path','rc','stderr'])
    by_name=defaultdict(list)
    for path,d in dynamic.items():
        by_name[Path(path).name].append(path)
        if d['soname'] and d['soname']!=Path(path).name:by_name[d['soname']].append(path)
    for v in by_name.values():v[:]=sorted(set(v))
    edges=[]; closures=[]; outside=[]; missing=[]
    for target in TARGETS:
        if target not in dynamic:
            missing.append(dict(target=target,parent='',needed='',reason='target ELF copy absent'))
            closures.append(dict(target=target,path=target,depth=0,status='target_absent'))
            continue
        queue=deque([(target,0)]); seen=set()
        while queue:
            parent,depth=queue.popleft()
            if parent in seen:continue
            seen.add(parent)
            closures.append(dict(target=target,path=parent,depth=depth,status='ELF copy present'))
            for needed in dynamic[parent]['needed']:
                candidates=by_name.get(needed,[])
                in_ld=[p for p in candidates if str(Path(p).parent) in LD_DIRS]
                chosen=(in_ld or candidates or [''])[0]
                status='missing_copy' if not chosen else 'in_ld_path' if chosen in in_ld else 'outside_ld_path'
                exact=bool(chosen and Path(chosen).name==needed)
                edge=dict(target=target,parent=parent,needed=needed,resolved_path=chosen,candidate_count=len(candidates),
                          exact_basename=int(exact),status=status,
                          in_ld_library_path=int(bool(chosen and str(Path(chosen).parent) in LD_DIRS)),
                          in_prelink_conf=int(bool(chosen and str(Path(chosen).parent) in CONF_DIRS)))
                edges.append(edge)
                if not chosen:missing.append(dict(target=target,parent=parent,needed=needed,reason='no saved ELF basename or SONAME match'))
                elif chosen not in in_ld:outside.append(edge)
                if chosen and chosen not in seen:queue.append((chosen,depth+1))
        log(f'closure {target}: {len(seen)} saved ELF paths')
    write('dependency_edges.tsv',edges,list(edges[0]))
    write('target_closure.tsv',closures,list(closures[0]))
    write('missing_copies.tsv',missing,['target','parent','needed','reason'])
    write('outside_ld_path.tsv',outside,list(edges[0]))
    # Do not create absent SONAME symlinks: list those namespace gaps explicitly.
    aliases=[]
    for e in edges:
        if e['resolved_path'] and not int(e['exact_basename']):
            aliases.append(dict(target=e['target'],parent=e['parent'],needed=e['needed'],candidate=e['resolved_path']))
    write('missing_soname_aliases.tsv',aliases,['target','parent','needed','candidate'])
    by_target=defaultdict(set)
    for e in outside:by_target[e['target']].add((e['needed'],e['resolved_path']))
    summary={'elf_copies':len(paths),'readelf_errors':len(errors),'targets':len(TARGETS),'missing_target_copies':sum(t not in dynamic for t in TARGETS),
             'missing_dependency_edges':len(missing),'missing_soname_alias_edges':len(aliases),'outside_ld_path_edges':len(outside),
             'targets_with_outside_ld_path':{t:sorted([{'needed':n,'path':p} for n,p in vals],key=lambda x:(x['needed'],x['path'])) for t,vals in by_target.items()},
             'libfkpInternal_paths':sorted(p for p in paths if Path(p).name=='libfkpInternal.so')}
    (HERE/'dependency_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    log(f"done: {len(edges)} needed edges, {len(outside)} outside, {len(missing)} missing")

if __name__=='__main__':
    state='成功'
    try:main()
    except BaseException:
        state='失败';raise
    finally:print('已结束',datetime.now(timezone.utc).isoformat(timespec='seconds'),'状态='+state,flush=True)
