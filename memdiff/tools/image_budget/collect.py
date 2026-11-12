#!/usr/bin/env python3
"""Read-only system r-xp pagemap collection: one SDB shell per PID."""
import argparse
import hashlib
import json
import time
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

READELF = Path('/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf')

HERE = Path(__file__).resolve().parent
PAGE = re.compile(r"^__PAGE_BEGIN__\t([^\t]+)\t([^\t]+)\t([^\t]+)\t(.+?)\t(\d+)$")
BODY = r'''set -o pipefail
pid=PID_PLACEHOLDER
if [ ! -r /proc/$pid/maps ] || [ ! -r /proc/$pid/smaps ] || [ ! -r /proc/$pid/pagemap ]; then
  printf '__EXITED__\n'
  exit 0
fi
printf '__MAPS_BEGIN__\n'
cat /proc/$pid/maps || exit 41
printf '__MAPS_END__\n'
printf '__SMAPS_BEGIN__\n'
cat /proc/$pid/smaps || exit 42
printf '__SMAPS_END__\n'
printf '__STATUS_BEGIN__\n'; cat /proc/$pid/status || exit 44; printf '__STATUS_END__\n'
printf '__CMDLINE_BEGIN__\n'; tr '\000' ' ' </proc/$pid/cmdline || exit 45; printf '\n__CMDLINE_END__\n'
printf '__EXE_BEGIN__\n'; readlink /proc/$pid/exe || true; printf '__EXE_END__\n'
while read -r address permission offset device inode path; do
  [ "$permission" = 'r-xp' ] || continue
  case "$path" in /*) ;; *) continue ;; esac
  start=${address%-*}
  end=${address#*-}
  pages=$(( (16#$end - 16#$start) / PAGE_SIZE_PLACEHOLDER ))
  skip=$(( 16#$start / PAGE_SIZE_PLACEHOLDER ))
  [ "$pages" -gt 0 ] || continue
  printf '__PAGE_BEGIN__\t%s\t%s\t%s\t%s\t%s\n' "$address" "$permission" "$offset" "$path" "$pages"
  dd if=/proc/$pid/pagemap bs=8 skip="$skip" count="$pages" 2>/dev/null | od -An -tx8 -v
  result=$?
  printf '__PAGE_END__\t%s\n' "$result"
  [ "$result" -eq 0 ] || exit 43
done < /proc/$pid/maps
printf '__DONE__\n'
'''


def stamp():
    return datetime.now(timezone.utc).isoformat()


def log(message):
    line = stamp() + ' ' + message
    HERE.mkdir(parents=True,exist_ok=True)
    with (HERE/'collect.log').open('a') as f:
        f.write(line+'\n')
    print(line, flush=True)


def save_json(state):
    (HERE / "collection.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def run(label, argv, records, timeout=120):
    raw = HERE / "raw"
    raw.mkdir(exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
    outpath, errpath = raw / (safe + ".stdout"), raw / (safe + ".stderr")
    log(label)
    try:
        with outpath.open("wb") as out, errpath.open("wb") as err:
            rc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        rc = 124
        with errpath.open("ab") as err:
            err.write(b"host timeout\n")
    records.append({"label": label, "argv": argv, "rc": rc,
                    "stdout": str(outpath.relative_to(HERE)), "stderr": str(errpath.relative_to(HERE))})
    output = outpath.read_text(errors="replace") if outpath.stat().st_size < 1024 * 1024 else ""
    return rc, output


def shell(ip, label, command, records, timeout=120, required=True):
    # sdb itself can return zero for a failed remote command. Keep the remote RC in-band.
    wrapped = "bash -c " + shlex.quote(command + "\nremote_rc=$?; printf '\\n__IMAGE_BUDGET_RC__%s\\n' \"$remote_rc\"")
    host_rc, output = run(label, ["sdb", "-s", ip, "shell", wrapped], records, timeout)
    record = records[-1]
    outpath = HERE / record["stdout"]
    raw = outpath.read_bytes()
    marker = re.search(rb"\n__IMAGE_BUDGET_RC__(\d+)\s*$", raw)
    rc = int(marker[1]) if marker and host_rc == 0 else (host_rc or 125)
    record["host_rc"] = host_rc
    record["remote_rc"] = int(marker[1]) if marker else None
    if marker:
        outpath.write_bytes(raw[:marker.start()])
        output = raw[:marker.start()].decode(errors="replace") if len(raw) < 1024*1024 else ""
    if required and rc:
        raise RuntimeError(f"{label}: sdb rc={rc}")
    return rc, output


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def pull_status(rc, local):
    return 'pull_failed' if rc or not local.is_file() else 'pulled'


def process_command(pid, page_size):
    script = BODY.replace("PID_PLACEHOLDER", str(pid)).replace("PAGE_SIZE_PLACEHOLDER", str(page_size))
    return "bash -c " + shlex.quote(script)


def steady_window(samples, memtotal):
    """Same 10 x 30 s window as memcheck; minimum uptime 600 s."""
    window = samples[-10:]
    if len(window) < 10 or window[-1]['uptime_s'] < 600:
        return False
    threshold = memtotal // 100
    return (max(x['available_kB'] for x in window) - min(x['available_kB'] for x in window) < threshold
            and max(x['swap_used_kB'] for x in window) - min(x['swap_used_kB'] for x in window) < threshold
            and sum(x['cpu_busy_percent'] for x in window) / 10 <= 21)


def collect_stability(ip, commands, state):
    """Sample for at most 30 minutes, recording the raw samples and capture reason."""
    script = "awk '/^cpu /{t=0;for(i=2;i<=NF;i++)t+=$i; print \"CPU\",t,$5+$6}' /proc/stat; " \
             "awk '/^(MemTotal|MemAvailable|SwapTotal|SwapFree):/{print $1,$2}' /proc/meminfo; " \
             "awk '{print \"UPTIME\",int($1)}' /proc/uptime"
    samples = []
    started = time.monotonic()
    previous = None
    while True:
        _, output = shell(ip, f'stability_{len(samples):03d}', script, commands)
        fields = {}
        for line in output.splitlines():
            parts = line.split()
            if parts:
                fields[parts[0].rstrip(':')] = parts[1:]
        needed = {'CPU', 'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree', 'UPTIME'}
        if not needed <= fields.keys():
            raise RuntimeError(f'incomplete stability sample: {sorted(fields)}')
        total, idle = map(int, fields['CPU'])
        busy = 0 if previous is None or total == previous[0] else (total-previous[0]-idle+previous[1])*100/(total-previous[0])
        previous = total, idle
        item = {'uptime_s': int(fields['UPTIME'][0]), 'available_kB': int(fields['MemAvailable'][0]),
                'swap_used_kB': int(fields['SwapTotal'][0])-int(fields['SwapFree'][0]),
                'cpu_busy_percent': busy, 'elapsed_s': round(time.monotonic()-started, 1)}
        samples.append(item)
        state['stability_samples'] = samples
        state['stable'] = steady_window(samples, int(fields['MemTotal'][0]))
        save_json(state)
        if state['stable'] or time.monotonic()-started >= 1800:
            state['capture_reason'] = 'steady_criteria_met' if state['stable'] else '按上限采集'
            state['capture_uptime_s'] = item['uptime_s']
            break
        time.sleep(30)


def check_tvs_prelink(ip, commands, state):
    local = HERE / 'identity' / 'tvs-daemon'
    local.parent.mkdir(exist_ok=True)
    rc, _ = run('pull_tvs_daemon', ['sdb', '-s', ip, 'pull', '/usr/bin/tvs-daemon', str(local)], commands)
    if rc or not local.is_file():
        state['tvs_daemon'] = {'status': 'pull_failed', 'rc': rc}
        return
    rc, _ = run('readelf_tvs_daemon', [str(READELF), '-hW', '-SW', '-dW', str(local)], commands)
    output = (HERE / 'raw/readelf_tvs_daemon.stdout').read_text(errors='replace')
    typ = re.search(r'^\s*Type:\s+(EXEC|DYN)\b', output, re.MULTILINE)
    state['tvs_daemon'] = {'status': 'ok' if rc == 0 else 'readelf_failed', 'sha256': sha(local),
                           'elf_type': typ[1] if typ else 'unknown',
                           'gnu_liblist': 'GNU_LIBLIST' in output,
                           'gnu_prelinked': 'GNU_PRELINKED' in output,
                           'prelink_undo': '.gnu.prelink_undo' in output}


def main(ip, out, expected_build_id=""):
    global HERE
    HERE = Path(out).resolve()
    HERE.mkdir(parents=True, exist_ok=True)
    commands = []
    state = {"ip": ip, "started_utc": stamp(), "commands": commands,
             "identity": {}, "processes": [], "pulled": [], "errors": []}
    initial_uid = None
    root_attempted = False
    status = "FAILED"
    try:
        for key, command in (("arch", "uname -m"), ("model", "cat /proc/device-tree/model"),
                             ("cmdline", "cat /proc/cmdline"), ("version", "cat /proc/version"),
                             ("os_release", "cat /etc/os-release"),
                             ("boot_id", "cat /proc/sys/kernel/random/boot_id"), ("uid", "id -u")):
            _, value = shell(ip, "identity_" + key, command, commands)
            state["identity"][key] = value.replace("\x00", "").replace("\r", "").strip()
        identity = state["identity"]
        initial_uid = identity["uid"]
        match = re.search(r'^BUILD_ID="?([^"\n]+)"?$', identity["os_release"], re.MULTILINE)
        state["build_id"] = match[1] if match else ""
        state["checks"] = {"armv7l": identity["arch"] == "armv7l",
                           "NT72671D": "NT72671D" in identity["model"],
                           "KSU2E": "KSU2E" in identity["cmdline"],
                           "BUILD_ID": bool(state["build_id"])}
        if expected_build_id:
            state["checks"]["expected_BUILD_ID"] = state["build_id"] == expected_build_id
        state["clang_kernel"] = "clang" in identity["version"].lower()
        save_json(state)
        if not all(state["checks"].values()):
            raise RuntimeError(f"identity gate failed: {state['checks']}")
        root_attempted = True
        rc, _ = run("root_on", ["sdb", "-s", ip, "root", "on"], commands, 30)
        if rc:
            raise RuntimeError(f"sdb root on: rc={rc}")
        for attempt in range(5):
            rc, uid = shell(ip, f"uid_root_{attempt}", "id -u", commands, required=False)
            if rc == 0 and uid.strip() == "0":
                break
        else:
            raise RuntimeError("root UID 0 not confirmed")
        _, boot = shell(ip, "boot_id_after_root", "cat /proc/sys/kernel/random/boot_id", commands)
        if boot.strip() != identity["boot_id"]:
            raise RuntimeError("boot ID changed")
        _, pg = shell(ip, "page_size", "getconf PAGESIZE", commands)
        page_size = int(pg.strip())
        state["page_size"] = page_size
        check_tvs_prelink(ip, commands, state)
        collect_stability(ip, commands, state)
        for name, remote in (("meminfo", "/proc/meminfo"), ("vmstat", "/proc/vmstat"),
                             ("zoneinfo", "/proc/zoneinfo"), ("pressure_memory", "/proc/pressure/memory"),
                             ("uptime", "/proc/uptime")):
            shell(ip, "snapshot_" + name, "cat " + remote, commands)
        zone = HERE/'raw/snapshot_zoneinfo.stdout'
        summary = [line for line in zone.read_text(errors='replace').splitlines()
                   if re.search(r'(^Node\s+\d+, zone|\s+(pages free|managed|present|min|low|high|protection):?\s)',line)]
        (HERE/'zoneinfo_summary.txt').write_text('\n'.join(summary)+'\n')
        _, conf = shell(ip, "prelink_conf", "cat /etc/prelink.conf", commands)
        state["prelink_conf"] = conf
        _, listing = shell(ip, "pids", "ls -d /proc/[0-9]*", commands)
        pids = sorted({int(x.rsplit("/", 1)[-1]) for x in listing.split() if x.rsplit("/", 1)[-1].isdigit()})
        if not pids:
            raise RuntimeError("empty PID list")
        state["pid_count_initial"] = len(pids)
        save_json(state)
        paths = set()
        for index, pid in enumerate(pids, 1):
            label = f"process_{pid}"
            rc, _ = shell(ip, label, process_command(pid, page_size), commands, timeout=180, required=False)
            rawpath = HERE / "raw" / (label + ".stdout")
            item = {"pid": pid, "rc": rc, "raw": str(rawpath.relative_to(HERE))}
            text = rawpath.read_text(errors="replace") if rc == 0 else ""
            item["status"] = ("command_failed" if rc else "exited_or_incomplete" if "__EXITED__" in text or "__DONE__" not in text else "complete")
            if item["status"] == "complete":
                for line in text.splitlines():
                    found = re.match(r"^[0-9a-f]+-[0-9a-f]+\s+[rwxps-]{4}\s+[0-9a-f]+\s+\S+\s+\d+\s+(/.*)$", line)
                    if found:
                        paths.add(found[1].removesuffix(" (deleted)"))
            state["processes"].append(item)
            if index % 20 == 0:
                log(f"process {index}/{len(pids)} complete={sum(x['status']=='complete' for x in state['processes'])} paths={len(paths)}")
                save_json(state)
        state["mapped_paths"] = sorted(paths)
        save_json(state)
        for index, path in enumerate(sorted(paths), 1):
            probe_command = ('if [ -f ' + shlex.quote(path) + ' ] && [ -r ' + shlex.quote(path) +
                             ' ]; then dd if=' + shlex.quote(path) +
                             ' bs=4 count=1 2>/dev/null | od -An -tx1; else exit 2; fi')
            probe_rc, magic = shell(ip, f'elf_probe_{index:04d}', probe_command, commands, required=False)
            if probe_rc or magic.split()[:4] != ['7f','45','4c','46']:
                state['pulled'].append({'path':path,'status':'not_elf_or_unreadable',
                                        'elf_probe_rc':probe_rc,'magic':magic.strip()})
                continue
            local = HERE / "elf" / path.lstrip("/")
            local.parent.mkdir(parents=True, exist_ok=True)
            rc, _ = run(f"pull_{index:04d}", ["sdb", "-s", ip, "pull", path, str(local)], commands, 180)
            item = {"path": path, "local": str(local.relative_to(HERE)), "pull_rc": rc}
            if pull_status(rc, local) == 'pull_failed':
                item["status"] = "pull_failed"
            else:
                item["size_bytes"] = local.stat().st_size
                item["host_sha256"] = sha(local)
                hash_rc, board_hash = shell(ip, f"hash_{index:04d}", "sha256sum " + shlex.quote(path), commands, required=False)
                words = board_hash.split()
                item["board_sha256"] = words[0] if hash_rc == 0 and words else ""
                item["status"] = "hash_match" if item["host_sha256"] == item["board_sha256"] else "hash_mismatch_or_unavailable"
                with local.open("rb") as stream:
                    item["is_elf"] = stream.read(4) == b"\x7fELF"
                if not item["is_elf"]:
                    local.unlink()
                    item["status"] = "not_elf"
            state["pulled"].append(item)
            if index % 25 == 0:
                log(f"pull {index}/{len(paths)}")
                save_json(state)
        status = "DONE"
    except Exception as error:
        state["errors"].append(f"{type(error).__name__}: {error}")
        log(f"FAILED {type(error).__name__}: {error}")
        raise
    finally:
        if root_attempted:
            run("root_off", ["sdb", "-s", ip, "root", "off"], commands, 30)
            rc, uid = shell(ip, "uid_after", "id -u", commands, required=False)
            state["root_restored"] = rc == 0 and uid.strip() != "0" and (initial_uid == "0" or uid.strip() == initial_uid)
            rc, boot = shell(ip, "boot_id_end", "cat /proc/sys/kernel/random/boot_id", commands, required=False)
            state["boot_id_unchanged"] = rc == 0 and boot.strip() == state.get("identity", {}).get("boot_id")
            if not state["root_restored"] or not state["boot_id_unchanged"]:
                status = "FAILED"
        state["status"] = status
        state["ended_utc"] = stamp()
        save_json(state)
        log(f"已结束 {state['ended_utc']} 状态={status}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ip")
    parser.add_argument("--out", required=True)
    parser.add_argument("--expected-build-id", default="")
    args = parser.parse_args()
    try:
        main(args.ip, args.out, args.expected_build_id)
    except Exception:
        sys.exit(1)
