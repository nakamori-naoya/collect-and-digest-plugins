#!/usr/bin/env python3
"""Strict, resumable playbook state stored outside the target repository."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile


def die(message: str, code: int = 2) -> None:
    print(f"[error] {message}", file=sys.stderr)
    raise SystemExit(code)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_config(path: str) -> tuple[dict, str]:
    try:
        raw = subprocess.run(
            ["yq", "-o=json", "-I=0", ".", path], check=True,
            text=True, capture_output=True,
        ).stdout
        config = json.loads(raw)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        die(f"解決済みplaybookを読めない: {path} ({exc})")
    playbook = config.get("playbook", config)
    canonical = json.dumps(playbook, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return playbook, hashlib.sha256(canonical.encode()).hexdigest()


def state_root() -> pathlib.Path:
    base = os.environ.get("XDG_STATE_HOME")
    if not base:
        base = str(pathlib.Path.home() / ".local" / "state")
    return pathlib.Path(base) / "harness-plugins" / "playbooks"


def safe(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        die(f"{label}に使えない文字がある: {value}")
    return value


def state_path(playbook: dict, run_id: str) -> pathlib.Path:
    return state_root() / safe(playbook["name"], "playbook名") / f"{safe(run_id, 'run-id')}.json"


def read_state(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        die(f"実行状態が無い: {path}")
    except json.JSONDecodeError:
        die(f"実行状態が壊れている: {path}")


def write_state(path: pathlib.Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    state["updated_at"] = now()
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(state, out, ensure_ascii=False, indent=2)
            out.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def checked(args: argparse.Namespace) -> tuple[dict, str, pathlib.Path, dict]:
    playbook, digest = load_config(args.config)
    path = state_path(playbook, args.run_id)
    state = read_state(path)
    if state.get("config_hash") != digest:
        die("playbook設定が開始時から変わったため再開できない")
    return playbook, digest, path, state


def command_init(args: argparse.Namespace) -> None:
    playbook, digest = load_config(args.config)
    path = state_path(playbook, args.run_id)
    if path.exists():
        state = read_state(path)
        if state.get("config_hash") != digest:
            die("同じrun-idのplaybook設定が変わっている")
        print(json.dumps({"status": "resumed", "state": str(path), "run_id": args.run_id}))
        return
    created = now()
    state = {
        "version": 1, "playbook": playbook["name"], "run_id": args.run_id,
        "config_hash": digest, "repo_root": str(pathlib.Path(args.repo).resolve()),
        "status": "running", "current_step": None, "artifacts": {},
        "created_at": created, "updated_at": created,
        "steps": [{"id": step["id"], "status": "pending", "attempts": 0,
                   "started_at": None, "completed_at": None, "error": None}
                  for step in playbook["steps"]],
    }
    write_state(path, state)
    print(json.dumps({"status": "initialized", "state": str(path), "run_id": args.run_id}))


def command_start(args: argparse.Namespace) -> None:
    playbook, _, path, state = checked(args)
    if state["status"] != "running" or state["current_step"] is not None:
        die("別の工程が実行中、またはplaybookが停止済み")
    pending = next((s for s in state["steps"] if s["status"] == "pending"), None)
    if not pending or pending["id"] != args.step:
        die(f"次に開始できる工程は {pending['id'] if pending else '無し'}")
    spec = next(s for s in playbook["steps"] if s["id"] == args.step)
    missing = [key for key in spec.get("needs", []) if key not in state["artifacts"]]
    if missing:
        die(f"開始条件を満たさない（不足: {', '.join(missing)}）")
    pending["status"] = "running"
    pending["attempts"] += 1
    pending["started_at"] = now()
    state["current_step"] = args.step
    write_state(path, state)
    print(json.dumps({"status": "running", "step": args.step, "attempt": pending["attempts"]}))


def provisions(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            die(f"--provideはkey=valueで渡す: {item}")
        key, value = item.split("=", 1)
        safe(key, "成果物名")
        if not value or key in result:
            die(f"成果物が空または重複: {key}")
        result[key] = value
    return result


def command_complete(args: argparse.Namespace) -> None:
    playbook, _, path, state = checked(args)
    if state["current_step"] != args.step:
        die(f"実行中の工程ではない: {args.step}")
    spec = next(s for s in playbook["steps"] if s["id"] == args.step)
    supplied = provisions(args.provide)
    expected = set(spec.get("provides", []))
    if set(supplied) != expected:
        die(f"完了成果物が一致しない（必要: {', '.join(sorted(expected))}）")
    record = next(s for s in state["steps"] if s["id"] == args.step)
    record["status"] = "completed"
    record["completed_at"] = now()
    state["artifacts"].update(supplied)
    state["current_step"] = None
    if all(s["status"] == "completed" for s in state["steps"]):
        state["status"] = "completed"
    write_state(path, state)
    print(json.dumps({"status": record["status"], "step": args.step, "playbook_status": state["status"]}))


def command_fail(args: argparse.Namespace) -> None:
    _, _, path, state = checked(args)
    if state["current_step"] != args.step:
        die(f"実行中の工程ではない: {args.step}")
    record = next(s for s in state["steps"] if s["id"] == args.step)
    record["status"] = "failed"
    record["error"] = args.reason
    state["current_step"] = None
    state["status"] = "failed"
    write_state(path, state)
    print(json.dumps({"status": "failed", "step": args.step, "reason": args.reason}))


def command_status(args: argparse.Namespace) -> None:
    _, _, path, state = checked(args)
    print(json.dumps({"state": str(path), **state}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "start", "complete", "fail", "status"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo", default=os.getcwd())
    parser.add_argument("--step")
    parser.add_argument("--provide", action="append", default=[])
    parser.add_argument("--reason", default="unspecified")
    args = parser.parse_args()
    if args.command in {"start", "complete", "fail"} and not args.step:
        die(f"{args.command}には--stepが要る")
    globals()[f"command_{args.command}"](args)


if __name__ == "__main__":
    main()
