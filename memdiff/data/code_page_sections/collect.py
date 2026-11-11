#!/usr/bin/env python3
"""Read-only SDB capture of smaps, pagemap and 13 ELF files; no board writes."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
EXPECTED_BUILD_ID = "T-KSU2EJAKUC-0101-PERF-202611061751"
OBJECTS = {
    "tvs-daemon": [
        "/usr/lib/libtvs-api-native.so", "/usr/lib/libtvs-dvb-si.so",
        "/usr/lib/libtvs-iss.so", "/usr/lib/libtvs-util.so",
        "/usr/lib/libtvs-dsm.so", "/usr/lib/libtvs-b2b.so",
        "/usr/lib/libtvs-dvbbase-scan.so", "/usr/lib/libtvs-atsc30-parser.so",
        "/usr/lib/libtvs-ext.so", "/usr/lib/libtvs-si.so",
    ],
    "tv-viewer": [
        "/usr/apps/org.tizen.tv-viewer/bin/tv-viewer",
        "/usr/lib/libtvs-parser.so", "/usr/lib/libtvs-api.so",
    ],
}
MAP = re.compile(r"^([0-9a-f]+)-([0-9a-f]+)\s+([rwxps-]{4})\s+([0-9a-f]+)\s+\S+\s+\d+\s*(.*?)\s*$")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_record(label, argv, timeout=60):
    """Never opens stdin; write exact stdout/stderr and return code to host files."""
    print(datetime.now(timezone.utc).isoformat(), label, flush=True)
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = 124, error.stdout or b"", error.stderr or b"timeout\n"
    record_dir = OUT / "raw"
    record_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
    (record_dir / (safe + ".stdout")).write_bytes(stdout)
    (record_dir / (safe + ".stderr")).write_bytes(stderr)
    return {"label": label, "argv": argv, "rc": code,
            "stdout_file": f"raw/{safe}.stdout", "stderr_file": f"raw/{safe}.stderr"}, stdout.decode(errors="replace")


def shell(ip, label, command, records, timeout=60):
    record, output = save_record(label, ["sdb", "-s", ip, "shell", command], timeout)
    records.append(record)
    if record["rc"]:
        raise RuntimeError(f"{label}: rc={record['rc']}; {record['stderr_file']}")
    return output


def parse_maps(text, wanted):
    results = []
    for line in text.splitlines():
        m = MAP.match(line)
        if not m:
            continue
        path = m[5].removesuffix(" (deleted)")
        if path not in wanted or m[3][:3] not in ("r-x", "r--", "rw-"):
            continue
        results.append({"start": int(m[1], 16), "end": int(m[2], 16),
                        "perms": m[3], "offset": int(m[4], 16), "path": path,
                        "maps_line": line})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ip")
    args = parser.parse_args()
    records = []
    metadata = {"ip": args.ip, "started_utc": datetime.now(timezone.utc).isoformat(), "commands": records}
    root_on = False
    original_uid = None
    try:
        identity = {}
        for label, cmd in (
            ("arch", "uname -m"), ("model", "cat /proc/device-tree/model"),
            ("cmdline", "cat /proc/cmdline"), ("version", "cat /proc/version"),
            ("os_release", "cat /etc/os-release"), ("uname", "uname -a"),
            ("uptime", "cat /proc/uptime"), ("boot_id", "cat /proc/sys/kernel/random/boot_id"),
            ("uid_before", "id -u")):
            identity[label] = (shell(args.ip, "identity_" + label, cmd, records)
                               .replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n"))
        original_uid = identity["uid_before"].strip()
        build_match = re.search(r'^BUILD_ID="?([^"\n]+)"?$', identity["os_release"], re.MULTILINE)
        build_id = build_match[1] if build_match else ""
        checks = {"armv7l": identity["arch"].strip() == "armv7l",
                  "NT72671D": "NT72671D" in identity["model"],
                  "KSU2E": "KSU2E" in identity["cmdline"],
                  "clang_kernel": "clang" in identity["version"].lower(),
                  "BUILD_ID": build_id == EXPECTED_BUILD_ID}
        metadata.update({"identity": identity, "build_id": build_id, "checks": checks})
        (OUT / "collection.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        if not all(checks.values()):
            raise RuntimeError(f"identity gate failed: {checks}; observed BUILD_ID={build_id!r}")

        root_on = True  # An attempted switch must always be followed by root off.
        record, _ = save_record("root_on", ["sdb", "-s", args.ip, "root", "on"])
        records.append(record)
        if record["rc"]:
            raise RuntimeError("sdb root on failed")
        for attempt in range(5):
            record, output = save_record(f"uid_root_{attempt}", ["sdb", "-s", args.ip, "shell", "id -u"])
            records.append(record)
            if record["rc"] == 0 and output.strip() == "0":
                break
            time.sleep(1)
        else:
            raise RuntimeError("expected root uid 0 after sdb root on")
        boot_after_root = shell(args.ip, "boot_id_after_root", "cat /proc/sys/kernel/random/boot_id", records).strip()
        if boot_after_root != identity["boot_id"].strip():
            raise RuntimeError("boot ID changed during root switch")
        page_size_text = shell(args.ip, "page_size", "getconf PAGESIZE", records).strip()
        page_size = int(page_size_text)
        metadata["page_size"] = page_size
        pids = {}
        mappings = []
        for process, wanted in OBJECTS.items():
            pid_output = shell(args.ip, "pidof_" + process, "pidof " + process, records)
            # Resolve from /proc/PID/exe, not just the command string.
            candidates = []
            for pid in sorted({int(value) for value in pid_output.split() if value.isdecimal()}):
                exe = shell(args.ip, f"exe_{process}_{pid}", f"readlink -f /proc/{pid}/exe", records).strip()
                if exe == ("/usr/bin/tvs-daemon" if process == "tvs-daemon" else "/usr/apps/org.tizen.tv-viewer/bin/tv-viewer"):
                    candidates.append(pid)
            if len(candidates) != 1:
                raise RuntimeError(f"expected one {process} process, got {candidates}")
            pid = candidates[0]
            pids[process] = pid
            maps = shell(args.ip, f"maps_{process}_{pid}", f"cat /proc/{pid}/maps", records)
            shell(args.ip, f"smaps_{process}_{pid}", f"cat /proc/{pid}/smaps", records, timeout=120)
            found = parse_maps(maps, wanted)
            absent = set(wanted) - {m["path"] for m in found}
            if absent:
                metadata.setdefault("missing_mapped_objects", {})[process] = sorted(absent)
            for number, m in enumerate(found):
                pages = (m["end"] - m["start"]) // page_size
                if pages <= 0 or (m["end"] - m["start"]) % page_size:
                    raise RuntimeError(f"bad VMA page alignment: {m}")
                label = f"pagemap_{process}_{number:03d}"
                cmd = f"bash -c 'set -o pipefail; dd if=/proc/{pid}/pagemap bs=8 skip={m['start']//page_size} count={pages} 2>/dev/null | od -An -tx8 -v'"
                output = shell(args.ip, label, cmd, records, timeout=120)
                words = output.split()
                if len(words) != pages:
                    raise RuntimeError(f"{label} returned {len(words)} entries, expected {pages}")
                m.update({"process": process, "pid": pid, "pages": pages, "pagemap_file": f"raw/{label}.stdout"})
                mappings.append(m)
            shell(args.ip, f"smaps_after_{process}_{pid}", f"cat /proc/{pid}/smaps", records, timeout=120)
        metadata["pids"] = pids
        metadata["mappings"] = mappings
        (OUT / "collection.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        pulled = []
        files = OUT / "elf"
        for path in sorted(set(sum(OBJECTS.values(), []))):
            local = files / path.lstrip("/")
            local.parent.mkdir(parents=True, exist_ok=True)
            record, _ = save_record("pull_" + path, ["sdb", "-s", args.ip, "pull", path, str(local)], timeout=180)
            records.append(record)
            if record["rc"] or not local.is_file():
                raise RuntimeError(f"pull failed: {path}")
            board_hash = shell(args.ip, "sha256_" + path, f"sha256sum {path}", records).split()[0]
            host_hash = sha(local)
            if board_hash != host_hash:
                raise RuntimeError(f"sha256 mismatch for {path}")
            pulled.append({"path": path, "local": str(local.relative_to(OUT)), "size_bytes": local.stat().st_size,
                           "board_sha256": board_hash, "host_sha256": host_hash})
        metadata["pulled"] = pulled
    finally:
        if root_on:
            record, _ = save_record("root_off", ["sdb", "-s", args.ip, "root", "off"])
            records.append(record)
            metadata["root_restored"] = False
            for attempt in range(5):
                record, output = save_record(f"uid_after_{attempt}", ["sdb", "-s", args.ip, "shell", "id -u"])
                records.append(record)
                if record["rc"] == 0 and output.strip() != "0" and (original_uid == "0" or output.strip() == original_uid):
                    metadata["root_restored"] = True
                    break
                time.sleep(1)
        metadata["ended_utc"] = datetime.now(timezone.utc).isoformat()
        (OUT / "collection.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    if not metadata.get("root_restored"):
        raise RuntimeError("root off / UID restore not confirmed")
    print("DONE", len(metadata["mappings"]), "mappings", len(metadata["pulled"]), "ELF", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAILED", type(error).__name__, str(error), file=sys.stderr, flush=True)
        raise
