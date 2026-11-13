#!/usr/bin/env python3
"""Read-only current-image prelink inventory and health probe."""
import csv
import gzip
import hashlib
import json
import re
import shlex
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "probe_raw"
RAW.mkdir(exist_ok=True)
IP = "192.168.108.26"
READELF = "/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf"
TARGETS = [
    "/usr/bin/tvs-daemon", "/usr/bin/TIFSDaemon", "/usr/bin/app-boot-manager",
    "/usr/apps/boot-helper-dyboost-tv/bin/boot-helper-dyboost-tv", "/usr/bin/fastinit",
    "/usr/bin/avocd", "/usr/bin/fastlogo", "/usr/bin/amd", "/usr/bin/fastvideo",
    "/usr/apps/org.tizen.tv-viewer/bin/tv-viewer", "/usr/bin/rscmgr-service",
    "/usr/bin/pulseaudio", "/usr/apps/org.tizen.btapp/bin/btapp",
    "/usr/bin/hdmicec-service", "/usr/apps/org.tizen.acm-service/bin/acm-service",
    "/usr/bin/launchpad-loader", "/usr/bin/launchpad-process-pool",
    "/usr/bin/app_launcher", "/usr/apps/org.tizen.welcome-mode/bin/welcome-mode",
]
DIRS = ["/opt/usr/apps/com.samsung.tv.slive-daemon/lib", "/lib", "/usr/lib",
        "/prd/usr/lib", "/usr/lib/was-api", "/usr/lib/ecore_imf/modules/isf/v-1.13",
        "/usr/lib/gstreamer-1.0", "/usr/lib/pulseaudio"]
records = []


def log(message):
    line = datetime.now(timezone.utc).isoformat() + " " + message
    print(line, flush=True)
    with (HERE / "progress.log").open("a") as stream:
        stream.write(line + "\n")


def run(name, argv, timeout=180):
    log("RUN " + name)
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = 124, e.stdout or b"", (e.stderr or b"") + b"\nTIMEOUT\n"
    (RAW / (name + ".stdout")).write_bytes(out)
    (RAW / (name + ".stderr")).write_bytes(err)
    rec = {"name": name, "argv": argv, "host_rc": rc, "stdout_bytes": len(out), "stderr_bytes": len(err)}
    records.append(rec)
    return rec, out.decode(errors="replace")


def board(name, cmd, timeout=180):
    wrapped = "bash -c " + shlex.quote(cmd + "; r=$?; printf '\n__PROBE_RC__%s\n' \"$r\"")
    rec, out = run(name, ["sdb", "-s", IP, "shell", wrapped], timeout)
    match = re.search(r"\n__PROBE_RC__(\d+)\s*$", out)
    rec["remote_rc"] = int(match[1]) if match else None
    rc = rec["host_rc"] or (rec["remote_rc"] if match else 125)
    return rc, out[:match.start()] if match else out


def sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def elf(path, index):
    local = HERE / "pulled" / path.lstrip("/")
    local.parent.mkdir(parents=True, exist_ok=True)
    rec, _ = run(f"pull_{index:04d}", ["sdb", "-s", IP, "pull", path, str(local)])
    if rec["host_rc"] or not local.is_file():
        return {"path": path, "error": "pull_failed", "pull_rc": rec["host_rc"]}
    rc, board_hash = board(f"sha_{index:04d}", "sha256sum " + shlex.quote(path))
    host_hash = sha(local)
    if rc or not board_hash.split() or board_hash.split()[0] != host_hash:
        return {"path": path, "error": "sha_mismatch", "host_sha256": host_hash,
                "board_sha256": board_hash.split()[0] if board_hash.split() else ""}
    outrec, output = run(f"readelf_{index:04d}", [READELF, "-hW", "-SW", "-dW", "-p", ".comment", str(local)])
    if outrec["host_rc"]:
        return {"path": path, "error": "readelf_failed", "readelf_rc": outrec["host_rc"]}
    kind = re.search(r"^\s*Type:\s+(EXEC|DYN)\b", output, re.M)
    return {"path": path, "type": kind[1] if kind else "unknown", "GNU_LIBLIST": "(GNU_LIBLIST)" in output,
            "GNU_PRELINKED": "(GNU_PRELINKED)" in output, "prelink_undo": ".gnu.prelink_undo" in output,
            "comment": " | ".join(x.strip() for x in re.findall(r"\[[^\]]+\]\s+([^\r\n]+)", output))[:600],
            "host_sha256": host_hash, "board_sha256": board_hash.split()[0], "bytes": local.stat().st_size}


def main():
    root = False
    result = {"identity": {}, "targets": [], "libraries": [], "commands": records}
    try:
        for name, cmd in [("arch", "uname -m"), ("model", "cat /proc/device-tree/model"),
                          ("cmdline", "cat /proc/cmdline"), ("build", "grep '^BUILD_ID=' /etc/os-release"),
                          ("version", "cat /proc/version"), ("boot_id", "cat /proc/sys/kernel/random/boot_id"),
                          ("uid", "id -u")]:
            rc, out = board("identity_" + name, cmd)
            if rc:
                raise RuntimeError(f"identity {name} rc={rc}")
            result["identity"][name] = out.replace("\x00", "").strip()
        i = result["identity"]
        if not (i["arch"] == "armv7l" and "NT72671D" in i["model"] and "KSU2E" in i["cmdline"]
                and i["build"] == "BUILD_ID=T-KSU2EJAKUC-0101-PERF-202611120549"):
            raise RuntimeError("identity gate failed")
        rec, _ = run("root_on", ["sdb", "-s", IP, "root", "on"], 30)
        root = True
        if rec["host_rc"]:
            raise RuntimeError("root on failed")
        rc, uid = board("uid_root", "id -u")
        if rc or uid.strip() != "0":
            raise RuntimeError("root UID not zero")
        rc, conf = board("prelink_conf", "cat /etc/prelink.conf")
        if rc:
            raise RuntimeError("prelink.conf unreadable")
        result["prelink_conf"] = conf
        for label, cmd in [
            ("failed_units", "systemctl --failed --no-legend --plain"),
            ("processes", "ps -eo pid,ppid,comm,args"),
            ("crash_files", "for d in /opt/usr/share/crash /opt/share/crash/dump /opt/share/crash; do if [ -d \"$d\" ]; then find \"$d\" -xdev -type f -printf '%p\\t%s\\t%TY-%Tm-%TdT%TH:%TM:%TS\\n'; fi; done | sort -u"),
            ("dmesg", "dmesg"),
            ("diagnostic_pulseaudio", "LD_DEBUG=libs /usr/bin/pulseaudio --version"),
        ]:
            rc, out = board(label, cmd, 180)
            result[label] = {"remote_rc": rc, "lines": len(out.splitlines())}
            if label.startswith("diagnostic_"):
                stderr = (RAW / (label + ".stderr")).read_text(errors="replace")
                result[label]["prelink_lines"] = [x for x in (out + stderr).splitlines()
                                                   if "prelink checking" in x.lower() or "vdprelink" in x.lower()]
        dirs = " ".join(shlex.quote(x) for x in DIRS)
        rc, lines = board("candidate_scan", f"for d in {dirs}; do if [ -d \"$d\" ]; then find \"$d\" -xdev -type f -exec grep -alF .gnu.prelink_undo {{}} +; fi; done", 600)
        if rc:
            raise RuntimeError(f"candidate scan rc={rc}")
        candidates = sorted(set(x.strip() for x in lines.splitlines() if x.strip().startswith("/")))
        result["candidate_count"] = len(candidates)
        for index, path in enumerate(TARGETS + [x for x in candidates if x not in TARGETS], 1):
            rc, _ = board(f"exists_{index:04d}", "test -f " + shlex.quote(path))
            if rc == 1 and path in TARGETS:
                result["targets"].append({"path": path, "exists": False})
                continue
            if rc:
                raise RuntimeError(f"existence check rc={rc} path={path}")
            item = elf(path, index)
            if path in TARGETS:
                item["exists"] = True
                result["targets"].append(item)
            else:
                result["libraries"].append(item)
            if index % 25 == 0:
                log(f"STATIC {index}/{len(TARGETS)+len(candidates)}")
                (HERE / "probe_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        (HERE / "probe_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    finally:
        if root:
            rec, _ = run("root_off", ["sdb", "-s", IP, "root", "off"], 30)
            rc, uid = board("uid_after", "id -u")
            result["root_restored"] = rec["host_rc"] == 0 and rc == 0 and uid.strip() == i["uid"]
            rc, boot = board("boot_id_after", "cat /proc/sys/kernel/random/boot_id")
            result["boot_id_unchanged"] = rc == 0 and boot.strip() == i["boot_id"]
        (HERE / "probe_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    state = "成功"
    try:
        main()
    except Exception as error:
        state = "失败"
        log(f"ERROR {error!r}")
        raise
    finally:
        log(f"已结束 {datetime.now(timezone.utc).isoformat()} 状态={state}")
