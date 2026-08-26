#!/usr/bin/env python3
"""Safely store one generated daily session digest."""

import argparse
import fcntl
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def fail(message, code=2):
    print(json.dumps({"error": message}, ensure_ascii=False))
    raise SystemExit(code)


def load(raw):
    result = subprocess.run(["yq", "-o=json", "-I=0", ".", raw], capture_output=True, text=True)
    if result.returncode:
        fail("resolved playbook config is unreadable")
    data = json.loads(result.stdout)
    return data.get("playbook", data)


def output_directory(raw):
    """Resolve an output directory without crossing a symlink or a regular file."""
    declared = Path(raw).expanduser().absolute()
    probe = declared
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if declared.is_symlink() or probe.is_symlink():
        fail("output dir must not be a symlink")
    if probe.exists() and not probe.is_dir():
        fail("output dir is not a directory")
    try:
        declared.mkdir(parents=True, exist_ok=True)
        os.chmod(declared, 0o700)
    except OSError as exc:
        fail("output dir cannot be created: {}".format(exc))
    # Check again after creation. A concurrent replacement must not turn the
    # destination into a symlink between the preflight and lock acquisition.
    if declared.is_symlink() or not declared.is_dir():
        fail("output dir must remain a real directory")
    return declared


def existing_hash(path):
    """Read only the front matter hash, never a body occurrence."""
    try:
        old = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail("existing digest cannot be read: {}".format(exc))
    front = re.match(r"\A---\n(.*?)\n---\n", old, re.DOTALL)
    if not front:
        return None
    match = re.search(r"^input_hash: ([0-9a-f]{64})$", front.group(1), re.MULTILINE)
    return match.group(1) if match else None


def metadata(path, session_count):
    source = Path(path)
    if source.is_symlink() or not source.is_file() or not source.stat().st_size:
        fail("metadata is absent or empty")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("metadata is unreadable: {}".format(exc))
    required = {"schema", "summary_schema", "sessions", "generator", "validation",
                "human_reviewed", "tags"}
    if not isinstance(data, dict) or data.get("schema") != 1 or required - data.keys():
        fail("metadata does not match schema 1")
    sessions = data["sessions"]
    if not isinstance(sessions, list) or len(sessions) != session_count:
        fail("metadata session count does not match")
    session_keys = {"source", "source_id", "observed_at"}
    if any(not isinstance(item, dict) or session_keys - item.keys() or
           any(not isinstance(item[key], str) or not item[key] for key in session_keys)
           for item in sessions):
        fail("metadata sessions are invalid")
    generator = data["generator"]
    if (not isinstance(generator, dict) or
            any(not isinstance(generator.get(key), str) or not generator[key]
                for key in ("model", "prompt_ref"))):
        fail("metadata generator is invalid")
    allowed_status = {"passed", "failed", "not_checked"}
    validation = data["validation"]
    required_checks = {"privacy", "structure", "source_unchanged"}
    if (not isinstance(validation, dict) or required_checks - validation.keys() or
            any(validation[key] not in allowed_status for key in required_checks)):
        fail("metadata validation is invalid")
    if "failed" in validation.values():
        fail("metadata contains a failed validation")
    if not isinstance(data["human_reviewed"], bool):
        fail("metadata human_reviewed must be boolean")
    tags = data["tags"]
    tag_keys = {"projects", "repositories", "purposes", "decisions", "open_questions"}
    if (not isinstance(tags, dict) or set(tags) != tag_keys or
            any(not isinstance(tags[key], list) or
                not all(isinstance(value, str) and value for value in tags[key])
                for key in tag_keys)):
        fail("metadata tags are invalid")
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True); parser.add_argument("--date", required=True)
    parser.add_argument("--input-hash", required=True); parser.add_argument("--body-file", required=True)
    parser.add_argument("--metadata-file", required=True)
    parser.add_argument("--timezone", required=True); parser.add_argument("--session-count", required=True, type=int)
    parser.add_argument("--force", action="store_true"); args = parser.parse_args()
    try:
        if datetime.strptime(args.date, "%Y-%m-%d").date().isoformat() != args.date:
            raise ValueError
    except ValueError:
        fail("date must be a real YYYY-MM-DD value")
    if not re.fullmatch(r"[0-9a-f]{64}", args.input_hash):
        fail("input hash must be sha256 hex")
    try:
        ZoneInfo(args.timezone)
    except Exception:
        fail("timezone must be a valid IANA timezone")
    body_path = Path(args.body_file)
    if body_path.is_symlink() or not body_path.is_file() or not body_path.stat().st_size:
        fail("body is absent or empty")
    try:
        body = body_path.read_text(encoding="utf-8")
    except OSError as exc:
        fail("body cannot be read: {}".format(exc))
    if not body.strip():
        fail("body is absent or empty")
    try:
        cfg = load(args.config)
        output = cfg["output"]
        output_dir = output["dir"]
    except (KeyError, TypeError):
        fail("resolved playbook config has no output.dir")
    out_dir = output_directory(output_dir)
    target = out_dir / (args.date + ".md")
    if target.is_symlink():
        fail("output file must not be a symlink")
    if args.session_count < 1:
        fail("session count must be positive")
    meta = metadata(args.metadata_file, args.session_count)
    content = "---\nschema: 2\nkind: agent-session-digest\ntarget_date: {}\ntimezone: {}\ninput_hash: {}\ngenerated_at: {}\nsession_count: {}\nsummary_schema: {}\nsessions: {}\ngenerator: {}\nvalidation: {}\nhuman_reviewed: {}\ntags: {}\n---\n\n{}".format(
        args.date, args.timezone, args.input_hash, datetime.now(timezone.utc).isoformat(),
        args.session_count, meta["summary_schema"],
        json.dumps(meta["sessions"], ensure_ascii=False, separators=(",", ":")),
        json.dumps(meta["generator"], ensure_ascii=False, separators=(",", ":")),
        json.dumps(meta["validation"], ensure_ascii=False, separators=(",", ":")),
        str(meta["human_reviewed"]).lower(),
        json.dumps(meta["tags"], ensure_ascii=False, separators=(",", ":")),
        body.rstrip() + "\n")
    lock_fd = os.open(out_dir / ".store.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(lock_fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists():
            if not target.is_file():
                fail("output file is not a regular file")
            if existing_hash(target) == args.input_hash:
                print(json.dumps({"decision": "unchanged", "path": str(target)})); return
            if not args.force:
                fail("daily digest input changed; inspect it and pass --force to replace", 3)
        fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=out_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content); handle.flush(); os.fsync(handle.fileno())
            os.replace(tmp, target)
        finally:
            try: os.unlink(tmp)
            except FileNotFoundError: pass
    print(json.dumps({"decision": "replaced" if args.force else "written", "path": str(target)}))


if __name__ == "__main__":
    main()
