#!/usr/bin/env python3
"""Prepare the UEP overlay probe without modifying any system ELF."""
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RAW.mkdir(parents=True, exist_ok=True)
IP = os.environ.get("UEP_BOARD_IP", "")
SDB = "/home/linhao/tizen-studio/tools/sdb"
READELF = "/home/linhao/GBS-ROOT-TOOLCHAIN-GCC-R4-20260714/local/BUILD-ROOTS/scratch.x86_64.0/usr/bin/armv7l-tizen-linux-gnueabi-readelf"
TOOL_DIR = Path("/tmp/prelink_undo_attr/usr/bin")
STAGE = "/root/uep_probe"
BUILD_ID = "T-KSU2EJAKUC-0101-PERF-202610010416"
SHORTLIST = ("whoami", "factor", "nproc", "numfmt", "shuf", "tsort", "seq", "yes", "basename", "dirname", "strings", "c++filt", "od", "sha256sum")

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def log(message):
    line = f"{now()} {message}"
    print(line, flush=True)
    with (HERE / "progress.log").open("a") as f:
        f.write(line + "\n")

def call(name, argv, timeout=90):
    log("RUN " + name)
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = 124, e.stdout or b"", (e.stderr or b"") + b"\nTIMEOUT\n"
    (RAW / f"{name}.stdout").write_bytes(out)
    (RAW / f"{name}.stderr").write_bytes(err)
    (RAW / f"{name}.json").write_text(json.dumps({"time": now(), "argv": argv, "rc": rc, "stdout_bytes": len(out), "stderr_bytes": len(err)}, ensure_ascii=False, indent=2) + "\n")
    log(f"END {name} rc={rc} stdout={len(out)} stderr={len(err)}")
    return rc, out.decode(errors="replace"), err.decode(errors="replace")

def remote(name, command, timeout=90):
    # sdb shell may report transport success even when the remote command fails.
    wrapped = command + "; __uep_rc=$?; printf '\\n__UEP_RC__%d\\n' \"$__uep_rc\""
    transport_rc, output, error = call(name, [SDB, "-s", IP, "shell", wrapped], timeout)
    match = re.search(r"\n__UEP_RC__(\d+)\s*$", output)
    if transport_rc or not match:
        return transport_rc or 255, output, error
    return int(match.group(1)), output[:match.start()], error

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def snapshot(label):
    remote(f"{label}_dmesg", "dmesg", 120)
    remote(f"{label}_dlog_main", "dlogutil -d -b main", 120)
    remote(f"{label}_dlog_system", "dlogutil -d -b system", 120)

def parse_fields(output):
    fields = {}
    for name in ("ARCH", "MODEL", "CMDLINE", "VERSION", "BUILD", "BOOTID", "UID"):
        m = re.search(r"__" + name + r"__\s*\n(.*?)(?=__[A-Z]+__|\Z)", output, re.S)
        fields[name] = m.group(1).strip().replace("\x00", "") if m else ""
    return fields

def identity():
    command = """printf '__ARCH__\\n'; uname -m; printf '__MODEL__\\n'; cat /proc/device-tree/model; printf '\\n__CMDLINE__\\n'; cat /proc/cmdline; printf '__VERSION__\\n'; cat /proc/version; printf '__BUILD__\\n'; sed -n 's/^BUILD_ID=//p' /etc/os-release; printf '__BOOTID__\\n'; cat /proc/sys/kernel/random/boot_id; printf '__UID__\\n'; id -u"""
    rc, output, _ = remote("identity", command)
    fields = parse_fields(output)
    checks = {"remote_rc": rc == 0, "armv7l": fields["ARCH"] == "armv7l", "NT72671D": "NT72671D" in fields["MODEL"], "KSU2E": bool(re.search(r"dtsversion=\S*KSU2E", fields["CMDLINE"])), "gcc_kernel": "gcc" in fields["VERSION"].lower(), "BUILD_ID": fields["BUILD"] == BUILD_ID, "boot_id": bool(fields["BOOTID"])}
    (HERE / "identity.json").write_text(json.dumps({"fields": fields, "checks": checks}, ensure_ascii=False, indent=2) + "\n")
    if not all(checks.values()):
        raise RuntimeError("identity check failed: " + json.dumps(checks, ensure_ascii=False))
    return fields

def root_on():
    rc, _, _ = call("root_on", [SDB, "-s", IP, "root", "on"])
    if rc: raise RuntimeError("sdb root on failed")
    rc, uid, _ = remote("root_uid", "id -u")
    if rc or uid.strip() != "0": raise RuntimeError("sdb root UID verification failed")

def root_off():
    rc, _, _ = call("root_off", [SDB, "-s", IP, "root", "off"])
    rc2, uid, _ = remote("sdk_uid", "id -u")
    if rc or rc2 or uid.strip() == "0": raise RuntimeError("sdb root off UID verification failed")

def attr_probe(state):
    rc, _, _ = remote("stage_absent", f"test ! -e {STAGE}")
    if rc: raise RuntimeError("stage directory already exists")
    rc, _, _ = remote("stage_create", f"mkdir -m 700 {STAGE}")
    if rc: raise RuntimeError("stage create failed")
    state["stage_created"] = True
    for name in ("getfattr", "setfattr"):
        source = TOOL_DIR / name
        if not source.is_file(): raise RuntimeError(f"official attr binary missing: {source}")
        rc, _, _ = call(f"push_{name}", [SDB, "-s", IP, "push", str(source), f"{STAGE}/{name}"], 120)
        if rc: raise RuntimeError(f"push {name} failed")
    snapshot("attr_before")
    tests = {
        "direct_version": f"{STAGE}/getfattr --version",
        "direct_xattrs": f"{STAGE}/getfattr -d -m - -e hex /usr/bin/tvs-daemon",
        "loader_version": f"/lib/ld-linux.so.3 {STAGE}/getfattr --version",
        "loader_xattrs": f"/lib/ld-linux.so.3 {STAGE}/getfattr -d -m - -e hex /usr/bin/tvs-daemon",
    }
    results = {}
    for name, command in tests.items():
        rc, out, err = remote(name, command)
        results[name] = {"rc": rc, "stdout": out, "stderr": err}
    snapshot("attr_after")
    (HERE / "attr_probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    return results

def candidate():
    for name in SHORTLIST:
        path = "/usr/bin/" + name
        tag = "candidate_" + name.replace("+", "plus")
        rc, _, _ = remote(tag + "_exists", f"test -f {path} && test ! -L {path}")
        if rc: continue
        rc, mapped, _ = remote(tag + "_mapped", f"grep -Fl {path} /proc/[0-9]*/maps 2>/dev/null")
        if rc == 0 or mapped.strip(): continue
        rc, refs, _ = remote(tag + "_references", f"grep -rFl {path} /etc /usr/lib/systemd/system 2>/dev/null", 120)
        if rc == 0 or refs.strip(): continue
        local = HERE / (name.replace("+", "plus") + ".original")
        rc, _, _ = call(tag + "_pull", [SDB, "-s", IP, "pull", path, str(local)], 120)
        if rc or not local.is_file(): continue
        with local.open("rb") as f:
            if f.read(4) != b"\x7fELF": continue
        r1, sections, _ = call(tag + "_sections", [READELF, "-SW", str(local)])
        r2, dynamic, _ = call(tag + "_dynamic", [READELF, "-dW", str(local)])
        if r1 or r2 or ".comment" not in sections or ".gnu.prelink_undo" in sections or any(x in dynamic for x in ("GNU_PRELINKED", "GNU_LIBLIST")): continue
        rc, baseline, _ = remote(tag + "_baseline", path + " --version")
        if rc: continue
        upper = "/opt/.overlay/platform/upperdir" + path
        lower = "/.org_rootfs" + path
        rc, check, _ = remote(tag + "_overlay", f"test ! -e {upper} && test -f {lower} && sha256sum {path} {lower}")
        if rc: continue
        hashes = re.findall(r"[0-9a-f]{64}", check)
        if len(hashes) != 2 or hashes[0] != hashes[1] or hashes[0] != sha(local): continue
        info = {"path": path, "name": name, "host_original": str(local), "sha256": hashes[0], "upper_path": upper, "lower_path": lower, "baseline_command": path + " --version", "baseline_output": baseline, "sections_output": str(RAW / (tag + "_sections.stdout"))}
        (HERE / "selected_candidate.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        log("SELECTED " + path)
        return info
    raise RuntimeError("no safe candidate met all conditions")

def main():
    if not IP: raise RuntimeError("UEP_BOARD_IP is required")
    state = {"start": now(), "ip": IP, "status": "RUNNING"}
    root_attempted = False
    try:
        rc, _, _ = call("connect", [SDB, "connect", IP], 30)
        if rc: raise RuntimeError("sdb connect failed")
        state["identity"] = identity()
        root_attempted = True
        root_on()
        state["attr_probe"] = attr_probe(state)
        state["candidate"] = candidate()
        state["status"] = "DONE"
    except BaseException as e:
        state["status"] = "FAILED"
        state["error"] = str(e)
        log("ERROR " + repr(e))
    finally:
        if root_attempted:
            if state.get("stage_created"):
                remote("stage_cleanup", f"rm -f {STAGE}/getfattr {STAGE}/setfattr; rmdir {STAGE}; test ! -e {STAGE}")
            try: root_off()
            except BaseException as e:
                state["status"] = "FAILED"
                state["cleanup_error"] = str(e)
        state["end"] = now()
        (HERE / "prepare_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return state["status"] == "DONE"

if __name__ == "__main__":
    ok = main()
    print("已结束", now(), "状态=" + ("成功" if ok else "失败"), flush=True)
    sys.exit(0 if ok else 1)
