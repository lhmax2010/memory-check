#!/usr/bin/env python3
"""Serial read-only overlay and library-closure capture via SDB.

Usage: collect_board.py IP. The script never reads stdin or writes to the board.
"""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time


HERE = Path(__file__).resolve().parent
RAW = HERE / "board"
RAW.mkdir(exist_ok=True)
PREVIOUS = HERE.parent / "prelink_bind_probe/identity_valid/os_release.json"
SO = re.compile(r"\.so(?:\.[^ /]+)?(?:$| \(deleted\)$)")
RC_MARKER = "__PREP_REMOTE_RC="


def run(name, argv, timeout=60):
    print("RUN", name, flush=True)
    out = RAW / (name + ".stdout")
    err = RAW / (name + ".stderr")
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    with out.open("wb") as stdout, err.open("wb") as stderr:
        try:
            p = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout,
                               stderr=stderr, timeout=timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "TIMEOUT"
    data = out.read_text(errors="replace").replace("\r", "")
    remote = re.findall(r"^" + RC_MARKER + r"(\d+)$", data, re.M)
    record = {"time_utc": started, "argv": argv, "sdb_rc": rc,
              "remote_rc": int(remote[-1]) if remote else None,
              "stdout_file": out.name, "stderr_file": err.name,
              "stdout_bytes": out.stat().st_size}
    (RAW / (name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
    print("DONE", name, "sdb_rc", rc, "remote_rc", record["remote_rc"],
          "bytes", out.stat().st_size, flush=True)
    return record, data


def shell(ip, name, body, timeout=60):
    wrapped = ("sh -c " + shlex.quote(body) +
               "; result=$?; printf '\\n" + RC_MARKER + "%s\\n' \"$result\"")
    return run(name, ["sdb", "-s", ip, "shell", wrapped], timeout)


def required(ip, name, body, timeout=60):
    record, data = shell(ip, name, body, timeout)
    if record["sdb_rc"] != 0 or record["remote_rc"] != 0:
        raise RuntimeError(f"{name} failed: {record}")
    return data.split(RC_MARKER, 1)[0].strip()


def partial_find(ip, name, body, timeout=60):
    record, data = shell(ip, name, body, timeout)
    if record["sdb_rc"] != 0 or record["remote_rc"] not in (0, 1):
        raise RuntimeError(f"{name} failed: {record}")
    if record["remote_rc"] == 1 and "Permission denied" not in data:
        raise RuntimeError(f"{name} failed for a reason other than permissions: {record}")
    return data.split(RC_MARKER, 1)[0].strip()


def ensure_connection(ip):
    record, data = run("sdb_devices_initial", ["sdb", "devices"])
    if ip not in data:
        run("sdb_connect", ["sdb", "connect", ip], 30)
        record, data = run("sdb_devices_after_connect", ["sdb", "devices"])
    if ip not in data or "device" not in data:
        raise RuntimeError("SDB target is not in device state")


def identity(ip):
    commands = {
        "uid": "id -u",
        "os_release": "cat /etc/os-release",
        "uname_m": "uname -m",
        "model": "cat /proc/device-tree/model",
        "cmdline": "cat /proc/cmdline",
        "version": "cat /proc/version",
        "boot_id": "cat /proc/sys/kernel/random/boot_id",
        "date": "date '+%Y-%m-%dT%H:%M:%S%z %s'",
        "uptime": "cat /proc/uptime",
    }
    got = {key: required(ip, "identity_" + key, cmd)
           for key, cmd in commands.items()}
    build = next((line.split("=", 1)[1] for line in got["os_release"].splitlines()
                  if line.startswith("BUILD_ID=")), "")
    previous = json.loads(PREVIOUS.read_text())["stdout"].replace("\r", "")
    expected = next((line.split("=", 1)[1] for line in previous.splitlines()
                     if line.startswith("BUILD_ID=")), "")
    checks = {"armv7l": got["uname_m"] == "armv7l",
              "NT72671D": "NT72671D" in got["model"],
              "KSU2E": "KSU2E" in got["cmdline"],
              "clang_kernel": "clang" in got["version"].lower(),
              "BUILD_ID_present": bool(build),
              "BUILD_ID_matches_previous_LLVM": bool(expected) and build == expected,
              "nonroot_before": got["uid"] == "5001"}
    (RAW / "identity_checks.json").write_text(json.dumps(
        {"checks": checks, "build_id": build, "expected_build_id": expected,
         "boot_id": got["boot_id"], "uid": got["uid"]}, indent=2) + "\n")
    if not all(checks.values()):
        raise RuntimeError("identity gate failed: " + repr(checks))
    return got


def overlay_mounts(mounts):
    result = []
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[2] != "overlay":
            continue
        opts = {}
        for option in parts[3].split(","):
            if "=" in option:
                k, v = option.split("=", 1)
                if k in ("lowerdir", "upperdir", "workdir"):
                    opts[k] = v
        result.append({"mountpoint": parts[1], "source": parts[0],
                       "options": parts[3], **opts})
    (HERE / "overlay_mounts.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def inventory_upper(ip, upper, index, lower):
    quoted = shlex.quote(upper)
    listing = partial_find(ip, f"upper{index}_inventory",
                           f"find {quoted} -xdev -printf '%p\\t%y\\t%s\\t%T@\\t%TY-%Tm-%TdT%TH:%TM:%TS\\t%m\\n'",
                           600)
    partial_find(ip, f"upper{index}_whiteouts",
                 f"find {quoted} -xdev -type c -exec stat -c '%n\\t%t\\t%T' {{}} +", 300)
    candidates = []
    for line in listing.splitlines():
        fields = line.split("\t")
        if len(fields) < 2 or fields[1] != "f" or not fields[0].startswith(upper + "/"):
            continue
        rel = fields[0][len(upper) + 1:]
        if rel.startswith(("usr/lib/", "usr/bin/", "lib/", "prd/usr/lib/")):
            candidates.append(fields[0])
    magic_body = r'''
for path do
  magic=$(od -An -tx1 -N4 "$path" 2>/dev/null) || magic=
  [ -n "$magic" ] || magic=ERROR
  printf '%s\t%s\n' "$path" "$magic"
done
'''
    for part, start in enumerate(range(0, len(candidates), 5)):
        command = ("sh -c " + shlex.quote(magic_body) + " sh " +
                   " ".join(map(shlex.quote, candidates[start:start + 5])))
        required(ip, f"upper{index}_elf_magic_{part:02d}", command, 180)
    if lower is None:
        return
    body = r'''
upper=$1
lower=$2
shift 2
for path do
  rel=${path#"$upper"/}
  source="$lower/$rel"
  usize=$(stat -c %s "$path" 2>/dev/null) || usize=
  [ -n "$usize" ] || usize=ERROR
  usha=$(sha256sum "$path" 2>/dev/null) || usha=
  [ -n "$usha" ] || usha=ERROR
  usha=${usha%% *}
  if [ -f "$source" ]; then
    lsize=$(stat -c %s "$source" 2>/dev/null) || lsize=
    [ -n "$lsize" ] || lsize=ERROR
    lsha=$(sha256sum "$source" 2>/dev/null) || lsha=
    [ -n "$lsha" ] || lsha=ERROR
    lsha=${lsha%% *}
    exists=1
  else
    exists=0; lsize=NA; lsha=NA
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$path" "$source" "$exists" "$usize" "$usha" "$lsize" "$lsha"
done
'''
    cmd = (f"find {quoted} -xdev -type f -exec sh -c {shlex.quote(body)} "
           f"sh {quoted} {shlex.quote(lower)} {{}} +")
    partial_find(ip, f"upper{index}_compare", cmd, 900)


def libraries_from_maps(text):
    result = set()
    for line in text.splitlines():
        if not re.match(r"^[0-9a-f]+-[0-9a-f]+\s", line):
            continue
        fields = line.split(None, 5)
        if len(fields) >= 6 and fields[5].startswith("/") and SO.search(fields[5]):
            result.add(fields[5].removesuffix(" (deleted)"))
    return result


def capture_closure(ip):
    by_process = {}
    for name in ("tvs-daemon", "tv-viewer", "TIFSDaemon"):
        raw = required(ip, "pidof_" + name, "pidof " + shlex.quote(name))
        pids = sorted({int(x) for x in raw.split() if x.isdecimal()})
        if not pids:
            raise RuntimeError("target process missing: " + name)
        by_process[name] = []
        for pid in pids:
            exe = required(ip, f"proc_{name}_{pid}_exe", f"readlink -f /proc/{pid}/exe")
            maps = required(ip, f"proc_{name}_{pid}_maps", f"cat /proc/{pid}/maps")
            required(ip, f"proc_{name}_{pid}_stat", f"cat /proc/{pid}/stat")
            by_process[name].append({"pid": pid, "exe": exe,
                                     "libraries": sorted(libraries_from_maps(maps))})
    (HERE / "process_closures.json").write_text(json.dumps(by_process, indent=2) + "\n")
    union = sorted({lib for runs in by_process.values() for run in runs
                    for lib in run["libraries"]})
    (HERE / "library_union_paths.txt").write_text("\n".join(union) + "\n")
    # Grouped remote commands avoid hundreds of SDB round trips. All operations
    # are read-only and serial on the board; no temporary board file is needed.
    body = r'''
for path do
  if [ -f "$path" ]; then
    hash=$(sha256sum "$path" 2>/dev/null) || hash=
    [ -n "$hash" ] || hash=ERROR
    hash=${hash%% *}
    pkg=$(rpm -qf "$path" 2>/dev/null) || pkg=
    [ -n "$pkg" ] || pkg=NOT_OWNED
    etype=$(od -An -tu2 -j 16 -N 2 "$path" 2>/dev/null) || etype=
    [ -n "$etype" ] || etype=ERROR
    size=$(stat -c %s "$path" 2>/dev/null) || size=
    [ -n "$size" ] || size=ERROR
    printf '%s\t%s\t%s\t%s\t%s\n' "$path" "$hash" "$pkg" "$etype" "$size"
  else
    printf '%s\tMISSING\tMISSING\tMISSING\tMISSING\n' "$path"
  fi
done
'''
    for index, start in enumerate(range(0, len(union), 5)):
        paths = union[start:start + 5]
        command = "sh -c " + shlex.quote(body) + " sh " + " ".join(map(shlex.quote, paths))
        required(ip, f"closure_metadata_{index:02d}", command, 240)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ip")
    ip = parser.parse_args().ip
    ensure_connection(ip)
    before = identity(ip)
    switched = False
    try:
        record, _ = run("sdb_root_on", ["sdb", "-s", ip, "root", "on"], 35)
        switched = True
        if record["sdb_rc"] != 0:
            raise RuntimeError("sdb root on failed")
        for attempt in range(5):
            record, got = shell(ip, f"uid_root_{attempt}", "id -u", 20)
            if record["remote_rc"] == 0 and got.split(RC_MARKER, 1)[0].strip() == "0":
                break
            time.sleep(1)
            run(f"reconnect_root_{attempt}", ["sdb", "connect", ip], 15)
        else:
            raise RuntimeError("root UID was not confirmed")
        if required(ip, "boot_id_after_root", "cat /proc/sys/kernel/random/boot_id") != before["boot_id"]:
            raise RuntimeError("boot ID changed after root switch")
        mounts = required(ip, "proc_mounts", "cat /proc/mounts")
        overlays = overlay_mounts(mounts)
        upper_text = required(ip, "upperdirs", "find /opt/.overlay -xdev -type d -name upperdir -print", 120)
        uppers = [line for line in upper_text.splitlines() if line.startswith("/opt/.overlay/")]
        (HERE / "upperdirs.json").write_text(json.dumps(uppers, indent=2) + "\n")
        for index, upper in enumerate(uppers):
            matches = [m for m in overlays if m.get("upperdir") == upper]
            mount = matches[0]["mountpoint"] if len(matches) == 1 else None
            lower = "/.org_rootfs" if mount == "/" else "/.org_rootfs" + mount if mount else None
            inventory_upper(ip, upper, index, lower)
        required(ip, "original_os_release_stat", "stat -c '%n\\t%s\\t%Y\\t%y' /.org_rootfs/etc/os-release")
        required(ip, "board_date", "date '+%Y-%m-%dT%H:%M:%S%z %s'")
        required(ip, "board_uptime", "cat /proc/uptime")
        required(ip, "prelink_conf", "cat /etc/prelink.conf")
        capture_closure(ip)
        if required(ip, "boot_id_end", "cat /proc/sys/kernel/random/boot_id") != before["boot_id"]:
            raise RuntimeError("boot ID changed during capture")
    finally:
        if switched:
            run("sdb_root_off", ["sdb", "-s", ip, "root", "off"], 35)
            for attempt in range(5):
                record, got = shell(ip, f"uid_restored_{attempt}", "id -u", 20)
                if record["remote_rc"] == 0 and got.split(RC_MARKER, 1)[0].strip() == before["uid"]:
                    break
                time.sleep(1)
                run(f"reconnect_restore_{attempt}", ["sdb", "connect", ip], 15)
            else:
                raise RuntimeError("original UID was not restored")
            if required(ip, "boot_id_restored", "cat /proc/sys/kernel/random/boot_id") != before["boot_id"]:
                raise RuntimeError("boot ID changed at cleanup")
    print("COLLECTION_DONE", flush=True)


if __name__ == "__main__":
    main()
