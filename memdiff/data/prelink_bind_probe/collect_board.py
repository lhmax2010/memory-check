#!/usr/bin/env python3
"""Noninteractive, serial SDB capture for the prelink bind-mount feasibility probe."""

import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time


IP = "192.168.108.26"
HERE = Path(__file__).resolve().parent
RAW = HERE / "board"
RAW.mkdir(exist_ok=True)
IDENTITY = HERE / "identity_valid"
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
SRC = f"/opt/usr/tmp_probe/prelink_bind_source_{STAMP}_{os.getpid()}"
DST = f"/opt/usr/prelink_bind_target_{STAMP}_{os.getpid()}"


def run(name, argv, timeout=45):
    print(f"RUN {name}", flush=True)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        rc, stdout, stderr = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as exc:
        rc = "TIMEOUT"
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
    (RAW / f"{name}.stdout").write_bytes(stdout)
    (RAW / f"{name}.stderr").write_bytes(stderr)
    meta = {"time_utc": started, "argv": argv, "rc": rc,
            "stdout_file": f"{name}.stdout", "stderr_file": f"{name}.stderr"}
    (RAW / f"{name}.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"DONE {name} rc={rc} bytes={len(stdout)}", flush=True)
    return rc, stdout.decode(errors="replace"), stderr.decode(errors="replace")


def shell(name, command, timeout=45):
    return run(name, ["sdb", "-s", IP, "shell", command], timeout)


def required(name, command, timeout=45):
    rc, out, err = shell(name, command, timeout)
    if rc != 0:
        raise RuntimeError(f"{name} failed: rc={rc}; {err[:240]}")
    return out.strip()


def remote_script(name, body, timeout=45):
    return shell(name, "sh -c " + shlex.quote(body), timeout)


def check_identity():
    checks = json.loads((IDENTITY / "checks.json").read_text())
    if not all(checks.values()):
        raise RuntimeError("recorded identity checks failed")
    prior = json.loads((IDENTITY / "boot_id.json").read_text())["stdout"].strip()
    now = required("boot_id_before_root", "cat /proc/sys/kernel/random/boot_id")
    if now != prior:
        raise RuntimeError("boot ID changed after identity check; stop and re-identify")
    uid = required("uid_before_root", "id -u")
    if uid != "5001":
        raise RuntimeError(f"unexpected initial UID {uid}; stop before root switch")
    return prior, uid


def bind_test():
    src, dst = SRC, DST
    body = f"""
set -u
src={shlex.quote(src)}
dst={shlex.quote(dst)}
base=/opt/usr/tmp_probe
created_dir=0
mounted=0
cleanup() {{
  if [ "$mounted" = 1 ]; then
    if umount "$dst"; then echo 'cleanup_umount=ok'; mounted=0; else echo 'cleanup_umount=FAILED'; return 1; fi
  fi
  rm -f "$src" "$dst" || return 1
  if [ "$created_dir" = 1 ]; then rmdir "$base" || return 1; fi
  echo 'cleanup_files=ok'
}}
trap cleanup EXIT
if [ -e "$src" ] || [ -e "$dst" ]; then echo 'probe_file_collision'; exit 2; fi
if [ -d "$base" ]; then echo 'tmp_probe_preexisting=1'; else
  mkdir "$base" || exit 3
  created_dir=1
  echo 'tmp_probe_preexisting=0'
fi
printf 'prelink-bind-source:{STAMP}\n' > "$src" || exit 4
: > "$dst" || exit 5
if [ -s "$dst" ]; then echo 'target_not_empty'; exit 6; fi
echo 'target_initially_empty=1'
mount --bind "$src" "$dst" || exit 7
mounted=1
echo 'bind_mount=ok'
cat "$dst" || exit 8
IFS= read -r observed < "$dst" || exit 9
if [ "$observed" != 'prelink-bind-source:{STAMP}' ]; then echo 'content_mismatch'; exit 9; fi
echo 'content_matches=1'
"""
    rc, out, err = remote_script("bind_selftest", body, 45)
    # A second, independent read-only check catches a failed trap.
    check = f"test ! -e {shlex.quote(src)} && test ! -e {shlex.quote(dst)} && ! grep -Fq {shlex.quote(dst)} /proc/self/mountinfo"
    clean_rc, _, _ = shell("bind_cleanup_verify", check)
    if clean_rc != 0:
        # The unique paths are ours. Recover only these, never system files.
        recovery = (
            f"if grep -Fq {shlex.quote(dst)} /proc/self/mountinfo; then "
            f"umount {shlex.quote(dst)} || exit 1; fi; "
            f"rm -f {shlex.quote(src)} {shlex.quote(dst)}"
        )
        if "tmp_probe_preexisting=0" in out:
            recovery += "; rmdir /opt/usr/tmp_probe"
        shell("bind_cleanup_recovery", recovery)
        after_rc, _, _ = shell("bind_cleanup_verify_after_recovery", check)
        if after_rc != 0:
            raise RuntimeError("bind probe cleanup could not be verified")
    return rc, out, err


def find_pids(name):
    rc, out, _ = shell(f"pidof_{name}", "pidof " + shlex.quote(name))
    if rc != 0:
        return []
    return sorted({int(x) for x in out.split() if re.fullmatch(r"[0-9]+", x)})


def capture_process(name, pid):
    prefix = f"proc_{name}_{pid}"
    exe = required(prefix + "_exe", f"readlink -f /proc/{pid}/exe")
    commands = {
        "comm": f"cat /proc/{pid}/comm",
        "cmdline": f"tr '\\000' ' ' < /proc/{pid}/cmdline",
        "cgroup": f"cat /proc/{pid}/cgroup",
        "status": f"cat /proc/{pid}/status",
        "stat": f"cat /proc/{pid}/stat",
        "maps": f"cat /proc/{pid}/maps",
        "smaps": f"cat /proc/{pid}/smaps",
        "auxv": f"od -An -tu4 /proc/{pid}/auxv",
        "rpm": "rpm -qf " + shlex.quote(exe),
        "file_stat": "stat -c '%a %A %f %n' " + shlex.quote(exe),
        "getcap": "getcap " + shlex.quote(exe),
        "elf_type": "od -An -tu2 -j 16 -N 2 " + shlex.quote(exe),
        "systemctl_status_pid": f"systemctl status {pid} --no-pager --full",
    }
    for key, cmd in commands.items():
        shell(prefix + "_" + key, cmd, 90 if key == "smaps" else 45)
    cgroup_text = (RAW / f"{prefix}_cgroup.stdout").read_text(errors="replace")
    units = re.findall(r"/([^/]+\.(?:service|scope))(?:/|$)", cgroup_text, re.M)
    unit = units[-1] if units else ""
    if unit:
        base = prefix + "_unit"
        shell(base + "_show", "systemctl show " + shlex.quote(unit) + " -p Id,Type,Restart,User,Group,SmackProcessLabel,CapabilityBoundingSet,Requires,Wants,After,PartOf,TriggeredBy,Triggers,ActiveState,SubState --no-pager")
        shell(base + "_cat", "systemctl cat " + shlex.quote(unit) + " --no-pager")
        shell(base + "_dependencies", "systemctl list-dependencies " + shlex.quote(unit) + " --all --no-pager", 60)
        shell(base + "_reverse", "systemctl list-dependencies --reverse " + shlex.quote(unit) + " --all --no-pager", 60)
    return {"name": name, "pid": pid, "exe": exe, "unit_from_cgroup": unit}


def main():
    prior_boot, prior_uid = check_identity()
    root_attempted = False
    records = []
    try:
        root_attempted = True
        rc, _, _ = run("sdb_root_on", ["sdb", "-s", IP, "root", "on"], 35)
        if rc != 0:
            raise RuntimeError("sdb root on failed")
        for attempt in range(5):
            rc, out, _ = shell(f"uid_root_{attempt}", "id -u", 20)
            if rc == 0 and out.strip() == "0":
                break
            time.sleep(1)
            run(f"reconnect_root_{attempt}", ["sdb", "connect", IP], 15)
        else:
            raise RuntimeError("root UID did not become 0")
        if required("boot_id_after_root", "cat /proc/sys/kernel/random/boot_id") != prior_boot:
            raise RuntimeError("boot ID changed after root switch")

        shell("mountinfo", "cat /proc/self/mountinfo")
        shell("df_opt_usr", "df -k /opt/usr")
        shell("fs_stat", "stat -f -c '%T %m %n' / /usr /usr/lib /usr/bin /opt/usr")
        bind_test()
        shell("command_prelink", "command -v prelink")
        shell("rpm_prelink", "rpm -qa | grep -i prelink")
        shell("prelink_config", "ls -ld /etc/prelink.conf /etc/prelink.conf.d")
        shell("find_prelink", "find / -xdev \\( -path /proc -o -path /sys \\) -prune -o -iname '*prelink*' -print", 100)
        if (RAW / "command_prelink.stdout").read_bytes().strip():
            shell("prelink_version", "prelink --version")
            shell("prelink_help", "prelink --help", 45)
        shell("ps_ef", "ps -ef")
        for name in ("tvs-daemon", "tv-viewer", "launchpad-loader", "TIFSDaemon"):
            for pid in find_pids(name):
                records.append(capture_process(name, pid))
        (RAW / "process_ledger.json").write_text(json.dumps(records, indent=2) + "\n")
        shell("true_binary", "if [ -x /bin/true ]; then echo /bin/true; elif [ -x /usr/bin/true ]; then echo /usr/bin/true; else echo NONE; fi")
        true_path = (RAW / "true_binary.stdout").read_text().strip()
        if true_path in ("/bin/true", "/usr/bin/true"):
            shell("ld_debug_true", "LD_DEBUG=libs " + true_path, 45)
        if required("boot_id_end", "cat /proc/sys/kernel/random/boot_id") != prior_boot:
            raise RuntimeError("boot ID changed during probe")
    finally:
        if root_attempted:
            run("sdb_root_off", ["sdb", "-s", IP, "root", "off"], 35)
            for attempt in range(5):
                rc, out, _ = shell(f"uid_restored_{attempt}", "id -u", 20)
                if rc == 0 and out.strip() == prior_uid:
                    break
                time.sleep(1)
                run(f"reconnect_restore_{attempt}", ["sdb", "connect", IP], 15)
            shell("boot_id_restored", "cat /proc/sys/kernel/random/boot_id")
    print("COLLECTION_DONE", flush=True)


if __name__ == "__main__":
    main()
