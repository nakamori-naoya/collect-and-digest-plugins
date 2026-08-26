#!/usr/bin/env python3
"""Build a private hand-off file from a session-collect day index."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

FIELDS = ["source", "source_id", "source_path", "source_fingerprint", "relation", "parent_source_id",
          "target_date", "display", "observed_at", "collector"]
REQUIRED_INDEX_KEYS = {"schema", "source", "source_id", "activity_dates", "relation",
                       "parent_source_id", "state", "provisional", "source_ref",
                       "observed_at", "collector"}


def fail(message, code=2):
    print(json.dumps({"error": message}, ensure_ascii=False))
    raise SystemExit(code)


def private_output_dir(raw):
    path = Path(raw).expanduser().absolute()
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if path.is_symlink() or probe.is_symlink():
        fail("material output dir must not be a symlink")
    if probe.exists() and not probe.is_dir():
        fail("material output dir is not a directory")
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
    except OSError as exc:
        fail("material output dir cannot be created: {}".format(exc))
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day-index", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--include-subagents", action="store_true")
    args = parser.parse_args()
    source = Path(args.day_index)
    if source.is_symlink() or not source.is_file():
        fail("day index is absent")
    records = []
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        fail("day index cannot be read: {}".format(exc))
    for number, line in enumerate(lines, 1):
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            fail("day index is malformed at line {}".format(number))
        if not isinstance(rec, dict):
            fail("day index record is not an object at line {}".format(number))
        if rec.get("schema") != 1:
            fail("day index has unknown schema at line {}".format(number))
        missing = REQUIRED_INDEX_KEYS - rec.keys()
        if missing:
            fail("day index record is missing required keys at line {}: {}".format(
                number, ", ".join(sorted(missing))))
        if (not isinstance(rec["source"], str) or not rec["source"] or
                not isinstance(rec["source_id"], str) or not rec["source_id"] or
                not isinstance(rec["activity_dates"], list) or
                not all(isinstance(day, str) for day in rec["activity_dates"]) or
                rec["relation"] not in {"root", "subagent"} or
                not isinstance(rec["provisional"], bool) or
                not isinstance(rec["source_ref"], dict) or
                not isinstance(rec["observed_at"], str) or not rec["observed_at"] or
                not isinstance(rec["collector"], str) or not rec["collector"]):
            fail("day index record has invalid fields at line {}".format(number))
        if args.date not in rec.get("activity_dates", []):
            continue
        if rec.get("provisional") or rec.get("state") != "quiescent":
            fail("session is not quiescent")
        source_path = rec.get("source_ref", {}).get("path")
        if not isinstance(source_path, str) or not source_path or not Path(source_path).is_file():
            fail("session source is missing")
        if Path(source_path).is_symlink():
            fail("session source must not be a symlink")
        fingerprint = rec.get("source_ref", {}).get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            fail("session source fingerprint is missing")
        records.append({
            "source": rec.get("source"), "source_id": rec.get("source_id"),
            "source_path": source_path,
            "source_fingerprint": fingerprint,
            "relation": rec.get("relation"),
            "parent_source_id": rec.get("parent_source_id"), "target_date": args.date,
            "display": rec.get("relation") != "subagent" or args.include_subagents,
            "observed_at": rec.get("observed_at"), "collector": rec.get("collector")
        })
    if not records:
        fail("対象日に完成済みのroot sessionが無い", 4)
    root_ids = {r["source_id"] for r in records if r["relation"] == "root"}
    if not root_ids:
        fail("対象日に完成済みのroot sessionが無い", 4)
    if any(r["relation"] == "subagent" and r["parent_source_id"] not in root_ids for r in records):
        fail("parentの無いsubagentがある")
    encoded = json.dumps(records, ensure_ascii=False, sort_keys=True).encode()
    input_hash = hashlib.sha256(encoded).hexdigest()
    out_dir = private_output_dir(args.out_dir)
    fd, path = tempfile.mkstemp(prefix="session-material-", suffix=".json", dir=out_dir)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(encoded)
    print(json.dumps({"decision": "written", "reason": "private material prepared",
        "artifact": {"material": path, "items": path, "target_date": args.date,
                     "input_hash": input_hash, "session_count": len(root_ids)},
        "counts": {"items": len(records)}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
