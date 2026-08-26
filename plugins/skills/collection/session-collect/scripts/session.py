#!/usr/bin/env python3
"""Claude Code / Codex session metadata indexer. Transcript bytes are never copied."""

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = 1


class CollectError(Exception):
    """Fatal: aborts the whole scan (malformed input, safety violation, index corruption)."""
    pass


class UnrecognizedSession(Exception):
    """Non-fatal: this one file is skipped with a reason; the scan continues.

    Raised for a JSONL file that parses fine but does not carry the target
    schema (e.g. a Workflow tool journal.jsonl with no Claude sessionId at
    all) or a session that legitimately has zero valid turns/timestamps yet
    (e.g. an almost-empty session file with only top-level ai-title/agent-name
    rows). Both are structurally valid JSON, just not a countable session.
    """

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def fail(message, code=2):
    print(json.dumps({"error": message}, ensure_ascii=False))
    raise SystemExit(code)


def load_config(raw):
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    result = subprocess.run(["yq", "-o=json", "-I=0", ".", raw],
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        fail("解決済みYAMLを読めない")
    return json.loads(result.stdout)


def plugin_version():
    manifest = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
    try:
        return json.loads(manifest.read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def iso(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def target_day(ts, zone):
    return ts.astimezone(zone).date().isoformat()


def safe_day(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError):
        raise CollectError("date must be a real YYYY-MM-DD value")
    if parsed != value:
        raise CollectError("date must be a real YYYY-MM-DD value")
    return value


def stable_lines(path, retries, max_bytes):
    """Read a stable prefix. Only an incomplete trailing line may be ignored."""
    for attempt in range(retries):
        before = path.stat()
        if before.st_size > max_bytes:
            raise CollectError("source exceeds max_source_bytes")
        with path.open("rb") as handle:
            data = handle.read(before.st_size)
        after = path.stat()
        stable = (before.st_ino, before.st_size, before.st_mtime_ns) == \
                 (after.st_ino, after.st_size, after.st_mtime_ns)
        if stable or attempt == retries - 1:
            provisional = not stable or (data and not data.endswith(b"\n"))
            raw_lines = data.splitlines(keepends=True)
            if data and not data.endswith(b"\n"):
                raw_lines = raw_lines[:-1]
            records = []
            for number, raw in enumerate(raw_lines, 1):
                try:
                    records.append((raw, json.loads(raw)))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise CollectError("malformed JSONL at line {}: {}".format(number, exc))
            return records, before, provisional
        time.sleep(0.05)
    raise AssertionError("unreachable")


def claude_meta(path, rows, source_stat, provisional):
    session_id = None; agent_id = None; started = None; ended = None; activity = set(); side = False
    for _, row in rows:
        if not isinstance(row, dict):
            continue
        row_session = row.get("sessionId")
        if row_session and session_id and row_session != session_id:
            raise CollectError("conflicting Claude sessionId values")
        session_id = session_id or row_session
        agent_id = agent_id or row.get("agentId")
        side = side or bool(row.get("isSidechain")) or "subagents" in path.parts
        ts = iso(row.get("timestamp"))
        if ts:
            started = ts if started is None or ts < started else started
            ended = ts if ended is None or ts > ended else ended
            activity.add(ts)
    if not session_id:
        raise UnrecognizedSession(
            "no Claude sessionId in any row (out-of-schema file, e.g. a Workflow journal.jsonl)")
    if not started:
        raise UnrecognizedSession(
            "Claude sessionId present but no valid timestamp yet (empty session)")
    native = session_id + ((":" + agent_id) if agent_id else "")
    return native, session_id if side else None, side, started, ended, activity, source_stat, provisional


def codex_meta(path, rows, source_stat, provisional):
    payload = None; started = None; ended = None; activity = set()
    for _, row in rows:
        if not isinstance(row, dict):
            continue
        ts = iso(row.get("timestamp"))
        if ts:
            started = ts if started is None or ts < started else started
            ended = ts if ended is None or ts > ended else ended
            activity.add(ts)
        if row.get("type") == "session_meta" and isinstance(row.get("payload"), dict):
            candidate = row["payload"]
            if payload and candidate.get("id") != payload.get("id"):
                raise CollectError("conflicting Codex session_meta id values")
            payload = payload or candidate
            pts = iso(payload.get("timestamp"))
            if pts:
                started = pts if started is None or pts < started else started
                ended = pts if ended is None or pts > ended else ended
                activity.add(pts)
    if not payload:
        raise UnrecognizedSession(
            "no Codex session_meta in any row (out-of-schema file)")
    native = payload.get("id")
    if not native or not started:
        raise CollectError("required Codex id/timestamp is absent")
    source = payload.get("source")
    side = payload.get("thread_source") == "subagent" or \
        (isinstance(source, dict) and bool(source.get("subagent")))
    parent = payload.get("parent_thread_id") or (payload.get("session_id") if side else None)
    return native, parent, side, started, ended, activity, source_stat, provisional


def source_files(cfg):
    include_subagents = cfg["collection"]["include_subagents"]
    maximum = cfg["collection"]["max_scan_files"]
    found = []
    for source, spec in cfg["sources"].items():
        if not spec["enabled"]:
            continue
        root = Path(os.path.expanduser(spec["root"]))
        if not root.is_dir():
            raise CollectError("enabled source root is absent: {}".format(source))
        for path in root.rglob("*.jsonl"):
            if source == "claude_code" and not include_subagents and "subagents" in path.parts:
                continue
            found.append((source, path))
            if len(found) > maximum:
                raise CollectError("max_scan_files exceeded")
    return found


def private_dir(path):
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if path.is_symlink() or probe.is_symlink():
        raise CollectError("state_dir must not pass through a symlink")
    # Reject before creating anything: an unignored git worktree must not gain
    # even an empty directory when the configuration is rejected.
    top = subprocess.run(["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode == 0:
        ignored = subprocess.run(["git", "-C", str(probe), "check-ignore", "-q", str(path)])
        if ignored.returncode != 0:
            raise CollectError("state_dir is inside a git worktree and is not ignored")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def salt_for(state_dir, dry_run):
    salt_path = state_dir / ".salt"
    if salt_path.exists():
        mode = stat.S_IMODE(salt_path.stat().st_mode)
        if mode & 0o077:
            raise CollectError("salt permissions are not private")
        return salt_path.read_bytes()
    if dry_run:
        return b"session-collect-dry-run"
    salt = secrets.token_bytes(32)
    fd = os.open(salt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(salt)
    return salt


def opaque(salt, source, native):
    return hmac.new(salt, (source + "\0" + native).encode(), hashlib.sha256).hexdigest()


def atomic_jsonl(path, records):
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for rec in records:
                handle.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass


def read_index(path):
    if not path.exists():
        return []
    out = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line: continue
        try: record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CollectError("index is malformed at line {}: {}".format(number, exc))
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            raise CollectError("index has unknown schema at line {}".format(number))
        if not (isinstance(record.get("source"), str) and record.get("source")
                and isinstance(record.get("source_id"), str) and record.get("source_id")
                and isinstance(record.get("started_at"), str) and record.get("started_at")):
            raise CollectError("index record is missing required keys at line {}".format(number))
        out.append(record)
    return out


def collect(cfg, requested_day, dry_run):
    requested_day = safe_day(requested_day)
    zone = ZoneInfo(cfg["timezone"]); state_dir = Path(cfg["state_dir"])
    if not dry_run: private_dir(state_dir)
    salt = salt_for(state_dir, dry_run)
    items = []; skipped = 0; unrecognized = []
    for source, path in source_files(cfg):
        try:
            rows, st, provisional = stable_lines(path, cfg["collection"]["stable_read_retries"],
                                                  cfg["collection"]["max_source_bytes"])
            parsed = claude_meta(path, rows, st, provisional) if source == "claude_code" \
                else codex_meta(path, rows, st, provisional)
            native, parent, side, started, ended, activity, st, provisional = parsed
            if side and not cfg["collection"]["include_subagents"]:
                skipped += 1
                continue
            activity_days = sorted({target_day(ts, zone) for ts in activity})
            if requested_day not in activity_days:
                continue
            item_id = opaque(salt, source, native)
            parent_id = opaque(salt, source, parent) if parent else None
            fingerprint = hashlib.sha256(b"".join(raw for raw, _ in rows)).hexdigest()
            quiescent = (time.time() - st.st_mtime) >= cfg["collection"]["quiescent_after_minutes"] * 60
            items.append({
                "schema": SCHEMA, "source": source, "source_id": item_id,
                "target_date": target_day(started, zone), "activity_dates": activity_days,
                "started_at": started.isoformat(), "last_event_at": ended.isoformat(),
                "relation": "subagent" if side else "root", "parent_source_id": parent_id,
                "state": "unknown" if provisional or not quiescent else "quiescent",
                "provisional": provisional, "source_ref": {"path": str(path.resolve()),
                    "bytes": st.st_size, "mtime_ns": st.st_mtime_ns, "fingerprint": fingerprint},
                "collector": "session-collect/" + plugin_version(),
                "observed_at": datetime.now(timezone.utc).isoformat()
            })
        # UnrecognizedSession: the file parsed as valid JSON but is either out of the
        # target schema (e.g. a Workflow tool journal.jsonl with no Claude sessionId)
        # or a legitimately empty session (sessionId present, zero valid timestamps
        # yet). Neither is a parse failure, so this one file is skipped with a
        # reason and the scan continues. A genuinely malformed JSONL still raises
        # CollectError below and aborts the whole scan, unchanged.
        except UnrecognizedSession as exc:
            unrecognized.append({
                "source": source, "path": str(path.resolve()), "reason": exc.reason,
                "observed_at": datetime.now(timezone.utc).isoformat()
            })
        except CollectError:
            raise
        except OSError as exc:
            raise CollectError("cannot inspect enabled source: {}".format(exc))
    if dry_run:
        return {"decision": "unchanged", "reason": "dry-run", "artifact": {
            "target_date": requested_day, "session_items": len(items),
            "provisional": sum(i["provisional"] for i in items)}, "counts": {
            "discovered": len(items), "written": 0, "updated": 0, "unchanged": 0,
            "skipped": skipped, "unrecognized": len(unrecognized),
            "provisional": sum(i["provisional"] for i in items)}}
    lock_path = state_dir / "lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(lock_fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index_path = state_dir / "index.jsonl"; existing = read_index(index_path)
        if not cfg["collection"]["include_subagents"]:
            existing = [r for r in existing if r.get("relation") != "subagent"]
        by_key = {(r["source"], r["source_id"]): r for r in existing}
        written = updated = unchanged = 0
        for item in items:
            key = (item["source"], item["source_id"])
            old = by_key.get(key)
            if old is None: written += 1
            elif old.get("source_ref", {}).get("fingerprint") == item["source_ref"]["fingerprint"]: unchanged += 1
            else: updated += 1
            by_key[key] = item
        merged = sorted(by_key.values(), key=lambda r: (r["source"], r["source_id"], r["started_at"]))
        atomic_jsonl(index_path, merged)
        # 該当ファイルをスキップ理由付きで記録する。この診断ログは私的な
        # state_dir 内だけに置き、原文pathを成功時のstdout報告へは出さない
        # （index.jsonlのsource_ref.pathと同じ扱い）。
        skipped_log = state_dir / "skipped.jsonl"
        atomic_jsonl(skipped_log, sorted(unrecognized, key=lambda r: (r["source"], r["path"])))
    decision = "updated" if updated else ("written" if written else "unchanged")
    return {"decision": decision, "reason": "session index reconciled", "artifact": {
        "target_date": requested_day, "index": str(index_path),
        "session_items": len(items), "provisional": sum(i["provisional"] for i in items),
        "skipped_log": str(skipped_log)},
        "counts": {"discovered": len(items), "written": written, "updated": updated,
                   "unchanged": unchanged, "skipped": skipped, "unrecognized": len(unrecognized),
                   "provisional": sum(i["provisional"] for i in items)}}


def main():
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan"); scan.add_argument("--config", required=True)
    scan.add_argument("--date", required=True); scan.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = collect(load_config(args.config), args.date, args.dry_run)
        print(json.dumps(result, ensure_ascii=False))
    except CollectError as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
