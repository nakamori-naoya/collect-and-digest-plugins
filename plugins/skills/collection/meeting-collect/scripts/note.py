#!/usr/bin/env python3
"""meeting-collect の決定的な部分。

冪等判定・ファイル書き出し・台帳更新・置き場の安全検査を担う。
意味的な判断（要約・抽出・秘匿の伏せ字）は一切しない。

  note.py check --config <json> --source notion --source-id X [--source-updated-at ISO]
      -> {"decision": "new"|"updated"|"unchanged", ...}

  note.py write --config <json> --source notion --source-id X --url U --title T
                --target-date YYYY-MM-DD --body-file /path/body.md [...]
      -> {"decision": "written"|"updated"|"unchanged", "path": "..."}

  note.py paths --config <json> --target-date YYYY-MM-DD
      -> {"notes_dir": "...", "date_dir": "..."}
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA = 1


from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "lib"))
import collection_store

def atomic_write(path, content):
    """同じdirectoryの一意な一時fileへ書き、競合せず置換する。"""
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp",
                               dir=os.path.dirname(path), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _plugin_version():
    """provenance の版はプラグイン本体の版に従わせる。

    定数で二重に持つと必ずずれる（実際 0.1.0 のまま取り残されていた）。
    """
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".claude-plugin", "plugin.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("version") or "unknown"
    except (OSError, ValueError):
        return "unknown"


COLLECTOR = "meeting-collect/" + _plugin_version()


def fail(msg, code=2):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(code)


def load_config(raw):
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    try:
        result = subprocess.run(
            ["yq", "-o=json", "-I=0", ".", raw], capture_output=True,
            text=True, timeout=10, check=True,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        fail("解決済みYAMLを読めない: {} ({})".format(raw, exc))


def canonical_id(source_id):
    """台帳のキーを1つに寄せる。

    Notion のページ ID は経路によってハイフン有り（UUID 形式）と無しの
    両方で返る。素の文字列で突き合わせると同じ議事録が別物として二重に
    保存されるため、32桁の16進に見えるものはハイフンを落として小文字化する。
    それ以外の ID（Drive のファイル ID など）はそのまま扱う。
    """
    s = (source_id or "").strip()
    bare = s.replace("-", "").lower()
    if len(bare) == 32 and all(c in "0123456789abcdef" for c in bare):
        return bare
    return s


def notes_dir(cfg):
    d = os.path.expanduser(cfg["notes_dir"])
    return os.path.abspath(d)


def index_path(cfg):
    return os.path.join(notes_dir(cfg), "index.jsonl")


def read_index(cfg):
    p = index_path(cfg)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                required = ['ts', 'source', 'path', 'content_hash', 'target_date', 'source_id']
                if not isinstance(entry, dict) or any(not isinstance(entry.get(key), str) or not entry[key] for key in required):
                    fail("台帳レコードschemaが壊れている。自動で読み飛ばさない")
                out.append(entry)
            except json.JSONDecodeError:
                fail("台帳に破損したJSON行がある。自動で読み飛ばさない")
    return out


def latest_record(cfg, source, source_id):
    key = canonical_id(source_id)
    found = None
    for rec in read_index(cfg):
        if rec.get("source") == source and canonical_id(rec.get("source_id")) == key:
            found = rec
    return found


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# source と source_id はファイル名になる。区切り文字も相対参照も入れない。
SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_date(d):
    """対象日はディレクトリ名になる。形式を固定してパス脱出を防ぐ。"""
    if not DATE_RE.match(d or ""):
        fail("target-date の形式が不正（YYYY-MM-DD のみ）: {!r}".format(d))
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        fail("target-date が実在しない日付: {!r}".format(d))
    return d


def safe_source(s):
    """source はファイル名の前半になる。収集元の識別子なので英小文字に限る。"""
    if not SOURCE_RE.match(s or ""):
        fail("source が不正（英小文字・数字・_・- のみ、32文字まで）: {!r}".format(s))
    return s


def safe_source_id(s):
    """source_id はファイル名の後半になる。

    Notion は32桁の16進、Drive は英数と _ - を返す。区切り文字や相対参照を
    含む値は上流の ID ではありえないので、落とさず拒否する。
    """
    if not SOURCE_ID_RE.match(s or "") or ".." in s:
        fail("source-id が不正（英数と . _ - のみ、128文字まで）: {!r}".format(s))
    return s


def ensure_within(base, path):
    """書き込み先が notes_dir の内側にあることを実パスで確かめる。

    個々の値を検査するだけでは、組み合わせや symlink による脱出を見落とす。
    実際に書く直前に、解決後のパスで最終確認する。
    """
    b = os.path.realpath(base)
    p = os.path.realpath(path)
    if p != b and not p.startswith(b + os.sep):
        fail("書き込み先が notes_dir の外を指した: {} （notes_dir: {}）".format(p, b))
    return path


def guard_dir(path):
    return collection_store.guard_dir(path, fail)


def yaml_scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def yaml_list(items):
    if not items:
        return "[]"
    return "[" + ", ".join(yaml_scalar(i) for i in items) + "]"


def build_front_matter(meta):
    lines = ["---"]
    lines.append("schema: {}".format(SCHEMA))
    for key in ("source", "source_id", "url", "title"):
        lines.append("{}: {}".format(key, yaml_scalar(meta.get(key))))
    lines.append("occurred_at: {}".format(yaml_scalar(meta.get("occurred_at"))))
    lines.append("attendees: {}".format(yaml_list(meta.get("attendees") or [])))
    lines.append("recording_url: {}".format(yaml_scalar(meta.get("recording_url"))))
    lines.append("fetched_at: {}".format(yaml_scalar(meta["fetched_at"])))
    lines.append("source_updated_at: {}".format(yaml_scalar(meta.get("source_updated_at"))))
    lines.append("content_hash: {}".format(yaml_scalar(meta["content_hash"])))
    lines.append("collector: {}".format(yaml_scalar(COLLECTOR)))
    lines.append("fidelity: markdown-lossy")
    lines.append("omitted: {}".format(yaml_list(meta.get("omitted") or [])))
    if meta.get("parts"):
        lines.append("parts:")
        for k, v in meta["parts"].items():
            lines.append("  {}: {}".format(k, yaml_scalar(v)))
    if meta.get("props"):
        lines.append("props:")
        for k, v in meta["props"].items():
            lines.append("  {}: {}".format(yaml_scalar(k), yaml_scalar(v)))
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def configured_timezone(cfg):
    try:
        return ZoneInfo(cfg["timezone"])
    except (KeyError, ZoneInfoNotFoundError):
        fail("timezone が不正: {!r}".format(cfg.get("timezone")))


def configured_now_iso(cfg):
    return datetime.now(configured_timezone(cfg)).isoformat(timespec="seconds")


def collector_result(decision, reason, artifact=None, counts=None):
    """Collector境界の共通envelope。判断と成果物を位置で推測させない。"""
    return {"decision": decision, "reason": reason,
            "artifact": artifact or {}, "counts": counts or {}}


def cmd_paths(args, cfg):
    args.target_date = safe_date(args.target_date)
    d = notes_dir(cfg)
    date_dir = os.path.join(d, args.target_date)
    print(json.dumps({"notes_dir": d, "date_dir": date_dir,
                      "index": index_path(cfg)}, ensure_ascii=False))


def cmd_check(args, cfg):
    root = notes_dir(cfg)
    guard_dir(root)
    with collection_store.locked(root):
        return cmd_check_locked(args, cfg)


def cmd_check_locked(args, cfg):
    rec = latest_record(cfg, args.source, args.source_id)
    if rec is None:
        decision = "new"
        reason = "台帳に無い"
    elif not os.path.exists(rec.get("path") or ""):
        # 実ファイルの有無を最優先で見る。台帳だけが「ある」と言い続けると、
        # 利用者が消したファイルが永久に復元されない。
        decision = "new"
        reason = "台帳にはあるが実ファイルが無い（消された）"
    elif args.source_updated_at and rec.get("source_updated_at") != args.source_updated_at:
        decision = "updated"
        reason = "source_updated_at が変わった"
    elif not args.source_updated_at:
        decision = "recheck"
        reason = "上流の更新時刻が取れないため本文を取得して hash で判定する"
    else:
        decision = "unchanged"
        reason = "source_updated_at が同じ"
    print(json.dumps(collector_result(
        decision, reason, {"path": (rec or {}).get("path")}, {"items": 1}), ensure_ascii=False))


def cmd_write(args, cfg):
    root = notes_dir(cfg)
    guard_dir(root)
    with collection_store.locked(root):
        return cmd_write_locked(args, cfg)


def cmd_write_locked(args, cfg):
    args.target_date = safe_date(args.target_date)
    d = notes_dir(cfg)
    date_dir = ensure_within(d, os.path.join(d, args.target_date))
    guard_dir(d)

    with open(args.body_file, encoding="utf-8") as f:
        body = f.read()

    max_bytes = int(cfg.get("collect", {}).get("max_bytes", 10485760))
    size = len(body.encode("utf-8"))
    if size > max_bytes:
        fail("本文が上限 {} バイトを超えた（{}）。途中で切った写しは作らない。".format(max_bytes, size))

    # 文字起こしは本文を書く前に読む。後から読むと、取得に失敗したときに
    # 「本文だけあって parts が指す先が無い」状態が残り、台帳にも載らない。
    parts = {}
    t_body = None
    if args.transcript_file:
        if not cfg.get("collect", {}).get("transcript"):
            fail("collect.transcript: false では --transcript-file を受け付けない")
        try:
            with open(args.transcript_file, encoding="utf-8") as tf:
                t_body = tf.read()
        except OSError as e:
            fail("transcript を読めない: {}".format(e))
        size += len(t_body.encode("utf-8"))
        if size > max_bytes:
            fail("本文とtranscriptが上限 {} バイトを超えた（{}）。途中で切った写しは作らない。".format(max_bytes, size))
        parts["transcript"] = "{}-{}.transcript.md".format(args.source, args.source_id)

    hash_seed = body.encode("utf-8") + b"\0" + ((t_body or "").encode("utf-8"))
    content_hash = "sha256:" + hashlib.sha256(hash_seed).hexdigest()
    rec = latest_record(cfg, args.source, args.source_id)

    filename = "{}-{}.md".format(args.source, args.source_id)
    path = ensure_within(d, os.path.join(date_dir, filename))

    props = {}
    if args.props:
        try:
            props = json.loads(args.props)
        except json.JSONDecodeError:
            fail("--props が JSON ではない")
        if not isinstance(props, dict):
            fail("--props はJSON objectに限る")
        if not all(isinstance(k, str) and isinstance(v, (str, int, float, bool, type(None))) for k, v in props.items()):
            fail("--props の値はscalarに限る")

    def opt(v):
        # 空文字は null にする。「取れなかった」を空文字で誤魔化さない。
        return v if v else None

    meta = {
        "source": args.source,
        "source_id": args.source_id,
        "url": args.url,
        "title": args.title,
        "occurred_at": opt(args.occurred_at),
        "attendees": [a for a in (args.attendees or "").split(",") if a],
        "recording_url": opt(args.recording_url),
        "fetched_at": configured_now_iso(cfg),
        "source_updated_at": opt(args.source_updated_at),
        "content_hash": content_hash,
        "omitted": [o for o in (args.omitted or "").split(",") if o],
        "parts": parts,
        "props": props,
    }

    record_meta = {k: v for k, v in meta.items() if k != "fetched_at"}
    record_meta["target_date"] = args.target_date
    record_hash = "sha256:" + hashlib.sha256(json.dumps(record_meta, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if rec is not None and rec.get("record_hash") == record_hash and os.path.exists(path) and all(os.path.exists(os.path.join(date_dir, part)) for part in parts.values()):
        print(json.dumps(collector_result("unchanged", "本文と全metadataが同じ", {"path": path}, {"items": 1}), ensure_ascii=False))
        return
    writes = {path: build_front_matter(meta) + body}
    # Old dates and superseded transcripts are archives, never deleted implicitly.

    t_path = None
    if t_body is not None:
        t_hash = "sha256:" + hashlib.sha256(t_body.encode("utf-8")).hexdigest()
        t_path = ensure_within(d, os.path.join(date_dir, parts["transcript"]))
        t_fm = [
            "---",
            "schema: {}".format(SCHEMA),
            "part: transcript",
            "parent: {}".format(yaml_scalar(args.source_id)),
            "source: {}".format(yaml_scalar(args.source)),
            "source_id: {}".format(yaml_scalar(args.source_id + "#transcript")),
            "url: {}".format(yaml_scalar(args.url)),
            "fetched_at: {}".format(yaml_scalar(meta["fetched_at"])),
            "content_hash: {}".format(yaml_scalar(t_hash)),
            "collector: {}".format(yaml_scalar(COLLECTOR)),
            "---",
            "",
            "",
        ]
        writes[t_path] = "\n".join(t_fm) + t_body

    os.makedirs(d, exist_ok=True)
    entry = {
        "ts": meta["fetched_at"],
        "source": args.source,
        "source_id": args.source_id,
        "source_updated_at": args.source_updated_at,
        "content_hash": content_hash,
        "record_hash": record_hash,
        "metadata": record_meta,
        "previous_path": rec.get("path") if rec else None,
        "path": path,
        "target_date": args.target_date,
        "title": args.title,
    }
    writes[index_path(cfg)] = collection_store.append_index(index_path(cfg), entry)
    collection_store.commit(d, writes)

    decision = "updated" if rec is not None else "written"
    print(json.dumps(collector_result(
        decision, "保存内容を更新" if rec is not None else "新規保存",
        {"path": path, "transcript_path": t_path},
        {"items": 1, "transcripts": 1 if t_path else 0}), ensure_ascii=False))


def run(fn, *a):
    """OSError を JSON のエラーへ寄せる。

    書けない場所を指されたときに Python の traceback が出ると、呼び出し側の
    エージェントは JSON を期待しているので解釈できず、失敗を握りつぶす。
    """
    try:
        return fn(*a)
    except (OSError, ValueError) as e:
        fail("ファイル操作に失敗した: {}".format(e))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--config", required=True)

    sp = sub.add_parser("paths")
    common(sp)
    sp.add_argument("--target-date", required=True)

    sp = sub.add_parser("check")
    common(sp)
    sp.add_argument("--source", required=True)
    sp.add_argument("--source-id", required=True)
    sp.add_argument("--source-updated-at", default="")

    sp = sub.add_parser("write")
    common(sp)
    sp.add_argument("--source", required=True)
    sp.add_argument("--source-id", required=True)
    sp.add_argument("--url", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--target-date", required=True)
    sp.add_argument("--body-file", required=True)
    sp.add_argument("--occurred-at", default="")
    sp.add_argument("--attendees", default="")
    sp.add_argument("--recording-url", default="")
    sp.add_argument("--source-updated-at", default="")
    sp.add_argument("--omitted", default="")
    sp.add_argument("--transcript-file", default="")
    sp.add_argument("--props", default="")

    args = p.parse_args()
    cfg = load_config(args.config)

    # ファイル名・front matter・台帳のすべてで同じキーを使う。
    if getattr(args, "source", None):
        args.source = safe_source(args.source)
        source_cfg = cfg.get("collect", {}).get("sources", {}).get(args.source)
        if not isinstance(source_cfg, dict) or source_cfg.get("enabled") is not True:
            fail("設定で無効または未定義のsourceは処理しない: {}".format(args.source))
    if getattr(args, "source_id", None):
        args.source_id = safe_source_id(canonical_id(args.source_id))

    if args.cmd == "paths":
        run(cmd_paths, args, cfg)
    elif args.cmd == "check":
        run(cmd_check, args, cfg)
    elif args.cmd == "write":
        run(cmd_write, args, cfg)


if __name__ == "__main__":
    main()
