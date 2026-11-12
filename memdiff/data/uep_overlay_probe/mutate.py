#!/usr/bin/env python3
"""Probe one non-running /usr/bin ELF and restore original bytes in finally."""
import hashlib
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

import prepare as p

HERE = p.HERE
STAGE = p.STAGE
STATE_PATH = HERE / "mutation_state.json"

def save(state):
    state["updated"] = p.now()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")

def remote(name, command, check=False, timeout=90):
    rc, out, err = p.remote(name, command, timeout)
    if check and rc:
        raise RuntimeError(f"{name} failed with remote rc={rc}: {out[-200:]} {err[-200:]}")
    return rc, out, err

def sha(path):
    return p.sha(path)

def snapshot(tag):
    p.snapshot(tag)

def metadata(tag, path, getfattr):
    commands = {
        "sha256": "sha256sum " + shlex.quote(path),
        "stat": "stat -c '%u %g %a %s' " + shlex.quote(path),
        "getcap": "/usr/sbin/getcap -n " + shlex.quote(path),
        "chsmack": "chsmack " + shlex.quote(path),
    }
    if getfattr:
        commands["xattrs"] = f"{STAGE}/getfattr -d -m - -e hex " + shlex.quote(path)
    result = {}
    for field, command in commands.items():
        rc, out, err = remote(f"{tag}_{field}", command)
        result[field] = {"rc": rc, "stdout": out, "stderr": err}
        if rc: raise RuntimeError(f"metadata {tag}.{field} rc={rc}")
    return result

def meta_equal(a, b):
    return {k: v["stdout"].strip() for k, v in a.items()} == {k: v["stdout"].strip() for k, v in b.items()}

def board_sha(name, path):
    _, out, _ = remote(name, "sha256sum " + shlex.quote(path), check=True)
    m = re.search(r"\b[0-9a-f]{64}\b", out)
    if not m: raise RuntimeError("sha256 output missing for " + path)
    return m.group()

def check_original(state, path):
    return board_sha("restore_sha", path) == state["original_sha256"]

def restore_xattrs(original, path):
    text = original.get("xattrs", {}).get("stdout", "")
    wanted = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", name): raise RuntimeError("unsafe xattr name")
            wanted[name] = value
    _, current, _ = remote("restore_xattrs_current", f"{STAGE}/getfattr -d -m - -e hex " + shlex.quote(path), check=True)
    have = {}
    for line in current.splitlines():
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            have[name] = value
    for name in sorted(set(have) - set(wanted)):
        remote("restore_xattr_remove_" + name.replace(".", "_"), f"{STAGE}/setfattr -x {shlex.quote(name)} {shlex.quote(path)}", check=True)
    for name, value in wanted.items():
        if have.get(name) != value:
            remote("restore_xattr_set_" + name.replace(".", "_"), f"{STAGE}/setfattr -n {shlex.quote(name)} -v {shlex.quote(value)} {shlex.quote(path)}", check=True)

def restore_metadata(state, path):
    original = state["metadata_before"]
    fields = original["stat"]["stdout"].split()
    if len(fields) < 4: raise RuntimeError("original stat not parseable")
    uid, gid, mode = fields[:3]
    if not all(re.fullmatch(r"\d+", x) for x in (uid, gid, mode)):
        raise RuntimeError("original uid/gid/mode not parseable")
    _, current, _ = remote("restore_stat_current", "stat -c '%u %g %a %s' " + shlex.quote(path), check=True)
    current_fields = current.split()
    if len(current_fields) < 3: raise RuntimeError("current stat not parseable")
    if current_fields[:2] != [uid, gid]:
        remote("restore_owner", f"chown {uid}:{gid} {shlex.quote(path)}", check=True)
    if current_fields[2] != mode:
        remote("restore_mode", f"chmod {mode} {shlex.quote(path)}", check=True)
    if "xattrs" in original:
        restore_xattrs(original, path)

def comment_offset(original):
    # The exact section offset is taken from the same platform cross readelf.
    sections = (p.RAW / "candidate_whoami_sections.stdout").read_text()
    match = re.search(r"\[\s*\d+\]\s+\.comment\s+PROGBITS\s+\S+\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)", sections)
    if not match: raise RuntimeError(".comment not found in platform readelf output")
    offset, size = int(match.group(1), 16), int(match.group(2), 16)
    data = Path(original).read_bytes()
    if size < 2 or offset + size > len(data) or data[offset] != ord("G"):
        raise RuntimeError("unexpected .comment bytes")
    return offset, size

def fallback_remove_upper(state, path):
    state["fallback_attempted"] = True
    save(state)
    upper = state["upper_path"]
    p.log("FALLBACK remove only the new upper file, then reboot")
    rc, _, _ = remote("fallback_upper_remove", "rm -f " + shlex.quote(upper) + "; test ! -e " + shlex.quote(upper))
    state["fallback_upper_remove_rc"] = rc
    save(state)
    if rc: raise RuntimeError("cannot remove upper copy")
    rc, _, _ = remote("fallback_sync", "sync")
    if rc: raise RuntimeError("sync after upper removal failed")
    rc, _, _ = p.call("fallback_reboot", [p.SDB, "-s", p.IP, "reboot"], 30)
    if rc: raise RuntimeError("reboot command failed")
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        time.sleep(10)
        r, _, _ = p.call("fallback_reconnect", [p.SDB, "connect", p.IP], 20)
        if r == 0:
            r2, out, _ = remote("fallback_uid", "id -u")
            if r2 == 0 and out.strip(): break
    else:
        raise RuntimeError("board did not reconnect within 15 minutes; user reflash may be needed")
    p.identity()
    state["fallback_sha256"] = board_sha("fallback_sha", path)
    rc, out, _ = remote("fallback_baseline", state["baseline_command"])
    state["fallback_run_rc"] = rc
    state["fallback_run_output"] = out
    state["restored"] = state["fallback_sha256"] == state["original_sha256"] and rc == state["baseline_rc"] and out.strip() == state["baseline_output"].strip()
    save(state)
    if not state["restored"]:
        raise RuntimeError("fallback did not restore baseline; user reflash may be needed")

def main():
    if not p.IP: raise RuntimeError("UEP_BOARD_IP is required")
    selected = json.loads((HERE / "selected_candidate.json").read_text())
    prep = json.loads((HERE / "prepare_state.json").read_text())
    if prep["status"] != "DONE" or prep["ip"] != p.IP:
        raise RuntimeError("prepare stage not complete for this IP")
    path = selected["path"]
    if path != "/usr/bin/whoami":
        raise RuntimeError("mutation is intentionally limited to reviewed /usr/bin/whoami")
    original = Path(selected["host_original"])
    if not original.is_file() or sha(original) != selected["sha256"]:
        raise RuntimeError("host original missing or hash changed")
    offset, size = comment_offset(original)
    modified = bytearray(original.read_bytes())
    modified[offset] = ord("H")
    expected_modified_sha = hashlib.sha256(modified).hexdigest()
    if expected_modified_sha != sha(HERE / "whoami.comment_modified"):
        raise RuntimeError("host modified reference hash mismatch")
    state = {"start": p.now(), "status": "RUNNING", "path": path, "upper_path": selected["upper_path"], "lower_path": selected["lower_path"], "original_sha256": selected["sha256"], "modified_sha256": expected_modified_sha, "comment_offset": offset, "comment_size": size, "stage_created": False, "touched": False, "restored": False, "baseline_command": selected["baseline_command"]}
    save(state)
    root_attempted = False
    try:
        rc, _, _ = p.call("mutation_connect", [p.SDB, "connect", p.IP], 30)
        if rc: raise RuntimeError("sdb connect failed")
        fields = p.identity()
        state["identity"] = fields
        if fields["BOOTID"] != prep["identity"]["BOOTID"]:
            raise RuntimeError("boot ID changed since candidate selection")
        root_attempted = True
        p.root_on()
        remote("mutation_stage_absent", f"test ! -e {STAGE}", check=True)
        remote("mutation_stage_create", f"mkdir -m 700 {STAGE}", check=True)
        state["stage_created"] = True; save(state)
        for name in ("getfattr", "setfattr"):
            src = p.TOOL_DIR / name
            if not src.is_file(): raise RuntimeError("attr tool missing: " + str(src))
            rc, _, _ = p.call("mutation_push_" + name, [p.SDB, "-s", p.IP, "push", str(src), f"{STAGE}/{name}"], 120)
            if rc: raise RuntimeError("attr push failed")
        remote("mutation_setfattr_version", f"{STAGE}/setfattr --version", check=True)
        remote("mutation_attr_test", f"touch {STAGE}/attr_test && {STAGE}/setfattr -n user.uep_probe -v test {STAGE}/attr_test && {STAGE}/getfattr -d -m - -e hex {STAGE}/attr_test && {STAGE}/setfattr -x user.uep_probe {STAGE}/attr_test && rm {STAGE}/attr_test", check=True)
        rc, _, _ = p.call("mutation_push_original", [p.SDB, "-s", p.IP, "push", str(original), f"{STAGE}/whoami.original"], 120)
        if rc: raise RuntimeError("original backup push failed")
        if board_sha("mutation_backup_sha", f"{STAGE}/whoami.original") != selected["sha256"]:
            raise RuntimeError("board backup SHA mismatch")
        if board_sha("mutation_target_sha", path) != selected["sha256"]:
            raise RuntimeError("target changed since selection")
        if board_sha("mutation_lower_sha", selected["lower_path"]) != selected["sha256"]:
            raise RuntimeError("lower file mismatch")
        remote("mutation_upper_absent", "test ! -e " + shlex.quote(selected["upper_path"]), check=True)
        rc, mapped, _ = remote("mutation_target_mapped", "grep -Fl " + shlex.quote(path) + " /proc/[0-9]*/maps 2>/dev/null")
        if rc == 0 or mapped.strip(): raise RuntimeError("target currently mapped")
        state["metadata_before"] = metadata("before", path, True)
        rc, out, _ = remote("mutation_baseline", selected["baseline_command"])
        state["baseline_rc"] = rc; state["baseline_output"] = out
        if rc != 0 or out.strip() != selected["baseline_output"].strip():
            raise RuntimeError("baseline execution changed since selection")
        snapshot("same_before")
        save(state)
        state["touched"] = True; save(state)
        remote("same_write", f"cat {STAGE}/whoami.original > {shlex.quote(path)}", check=True)
        state["same_sha256"] = board_sha("same_sha", path)
        remote("same_upper_present", "test -f " + shlex.quote(selected["upper_path"]), check=True)
        state["same_metadata"] = metadata("same", path, True)
        state["same_metadata_equal"] = meta_equal(state["metadata_before"], state["same_metadata"])
        if state["same_sha256"] != selected["sha256"]:
            raise RuntimeError("same-content write changed bytes unexpectedly")
        rc, out, _ = remote("same_run", selected["baseline_command"])
        state["same_run_rc"] = rc; state["same_run_output"] = out
        state["same_executes"] = rc == 0 and out.strip() == state["baseline_output"].strip()
        snapshot("same_after")
        save(state)
        snapshot("modified_before")
        # POSIX printf octal 110 writes one H byte; dd does not truncate.
        remote("modified_write", f"printf '\\110' | dd of={shlex.quote(path)} bs=1 seek={offset} count=1 conv=notrunc", check=True)
        state["modified_actual_sha256"] = board_sha("modified_sha", path)
        if state["modified_actual_sha256"] != expected_modified_sha:
            raise RuntimeError("modified file differs from one-byte .comment reference")
        state["modified_metadata"] = metadata("modified", path, True)
        rc, out, _ = remote("modified_run", selected["baseline_command"])
        state["modified_run_rc"] = rc; state["modified_run_output"] = out
        state["modified_executes"] = rc == 0 and out.strip() == state["baseline_output"].strip()
        snapshot("modified_after")
        save(state)
        state["status"] = "PROBED"
    except BaseException as e:
        state["status"] = "FAILED"
        state["error"] = str(e)
        p.log("ERROR " + repr(e))
    finally:
        if root_attempted and state["touched"]:
            try:
                snapshot("restore_before")
                remote("restore_write", f"cat {STAGE}/whoami.original > {shlex.quote(path)}", check=True)
                restore_metadata(state, path)
                state["restore_metadata"] = metadata("restored", path, True)
                state["restore_metadata_equal"] = meta_equal(state["metadata_before"], state["restore_metadata"])
                state["restore_sha256"] = board_sha("restored_sha", path)
                rc, out, _ = remote("restored_run", state["baseline_command"])
                state["restored_run_rc"] = rc; state["restored_run_output"] = out
                snapshot("restore_after")
                state["restored"] = state["restore_sha256"] == state["original_sha256"] and state["restore_metadata_equal"] and rc == state["baseline_rc"] and out.strip() == state["baseline_output"].strip()
                save(state)
                if not state["restored"]:
                    fallback_remove_upper(state, path)
            except BaseException as e:
                state["restore_error"] = str(e)
                state["status"] = "FAILED"
                p.log("RESTORE ERROR " + repr(e))
                if not state.get("fallback_attempted"):
                    try:
                        fallback_remove_upper(state, path)
                    except BaseException as e2:
                        state["fallback_error"] = str(e2)
                        p.log("FALLBACK ERROR " + repr(e2))
        if root_attempted:
            if state["stage_created"] and state["restored"]:
                cleanup_rc, _, _ = remote("mutation_stage_cleanup", f"rm -f {STAGE}/getfattr {STAGE}/setfattr {STAGE}/whoami.original {STAGE}/attr_test; rmdir {STAGE}; test ! -e {STAGE}")
                if cleanup_rc:
                    state["status"] = "FAILED"
                    state["cleanup_error"] = f"stage cleanup rc={cleanup_rc}"
            try:
                p.root_off()
            except BaseException as e:
                state["root_off_error"] = str(e)
                state["status"] = "FAILED"
        state["end"] = p.now()
        if not state["restored"]: state["status"] = "FAILED"
        save(state)
    return state["status"] == "PROBED" and state["restored"]

if __name__ == "__main__":
    ok = main()
    print("已结束", p.now(), "状态=" + ("成功" if ok else "失败"), flush=True)
    sys.exit(0 if ok else 1)
