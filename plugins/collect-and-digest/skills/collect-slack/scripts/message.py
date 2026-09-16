#!/usr/bin/env python3
"""collect-slack の決定的な部分。

冪等判定・ファイル書き出し・台帳更新・置き場の安全検査を担う。
何を集めるかの判断（対象の選定・検索クエリ）はしない。

  message.py paths --config <json> --target-date YYYY-MM-DD

  message.py check --config <json> --bucket <bucket> --latest-ts <ts>
      -> {"decision": "new"|"updated"|"unchanged", "known_ts": "..."}

  message.py append --config <json> --bucket <bucket> --target-date YYYY-MM-DD
                    --messages-file <jsonl> [--label "#dev"] [--url ...]
      -> {"decision": "...", "path": "...", "added": N, "total": N}

bucket は保存の単位。チャンネルなら channel ID、メンション束なら "mentions" など。
messages-file は1行1 JSON:
  {"ts":"1723526400.000100","user":"U123","user_name":"naoya","text":"…",
   "thread_ts":"…","permalink":"https://…","matched":"mention_direct"}
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
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

SCHEMA = 1

REDACTION_NOTE = "[REDACTED: possible credential material — see original]"

# 既知の認証情報フォーマットへの機械的・決定的な一致だけを見る。
#
# README冒頭の「伏せ字（redaction）はしない」は**意味的な機密判断**を指す —
# 「これは機密っぽい」という解釈は検出漏れが必ずあるため、偽の安心を売らない
# という方針である。ここはその逆で、解釈を一切挟まない固定フォーマットへの
# 一致だけを見る決定的処理であり、矛盾しない。
_PEM_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
_AWS_ACCESS_KEY_ID = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_GITHUB_TOKEN = re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b")
_SLACK_TOKEN = re.compile(r"\bxox[abpr]-[0-9A-Za-z-]{10,}\b")
CREDENTIAL_PATTERNS = [
    ("pem_private_key", _PEM_PRIVATE_KEY),
    ("aws_access_key_id", _AWS_ACCESS_KEY_ID),
    ("github_token", _GITHUB_TOKEN),
    ("slack_token", _SLACK_TOKEN),
]


def _looks_like_gcp_service_account_json(text):
    """GCPサービスアカウントJSONの典型的な鍵の組が揃っているかだけを見る。

    1キーだけでは一般的すぎて誤検知するので、type/private_key/client_email の
    3つが揃って初めて一致とする。JSONとして厳密にparseせず文字列一致にする
    のは、Slackの本文はコードブロックや引用で崩れていることがあり、
    「典型的な鍵の組が全部ある」こと自体が十分に高確度だからである。
    """
    return ('"type"' in text and '"service_account"' in text
            and '"private_key"' in text and '"client_email"' in text)


def detect_credential(text):
    """既知の認証情報フォーマットに一致したパターン名を返す。無ければNone。"""
    if not text:
        return None
    for name, pattern in CREDENTIAL_PATTERNS:
        if pattern.search(text):
            return name
    if _looks_like_gcp_service_account_json(text):
        return "gcp_service_account_json"
    return None
def _plugin_version():
    """provenance の版はプラグイン本体の版に従わせる。

    定数で二重に持つと必ずずれる（実際 0.1.0 のまま取り残されていた）。
    """
    p = Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("version") or "unknown"
    except (OSError, ValueError):
        return "unknown"


COLLECTOR = "collect-slack/" + _plugin_version()


def fail(msg, code=2):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(code)


ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _read_yaml(path):
    try:
        result = subprocess.run(["yq", "-o=json", "-I=0", ".", path], capture_output=True,
                                text=True, timeout=10, check=True)
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        fail("設定fileを読めない: {} ({})".format(path, exc))


def _channel_id(channel):
    return channel if isinstance(channel, str) else channel.get("id")


def validate_config(cfg, path):
    """collect-slack設定の閉じたschema検査。key集合・型・値の許容範囲を見る。fallbackは無い。"""
    if not isinstance(cfg, dict):
        fail("設定がmappingではない: {}".format(path))
    if set(cfg) != {"version", "slack_dir", "timezone", "collect"}:
        fail("設定のtop-level keyがschemaと一致しない（version / slack_dir / timezone / collect）: {}".format(path))
    if cfg["version"] != 1 or type(cfg["version"]) is not int:
        fail("versionは1だけを受け付ける")
    for key in ("slack_dir", "timezone"):
        if not isinstance(cfg[key], str) or not cfg[key]:
            fail("{} は空でない文字列".format(key))
    collect = cfg["collect"]
    if not isinstance(collect, dict) or set(collect) != {"channels", "targets", "groups", "max_bytes", "credential_redaction"}:
        fail("collect のkeyは channels / targets / groups / max_bytes / credential_redaction")
    if not isinstance(collect["max_bytes"], int) or isinstance(collect["max_bytes"], bool) or collect["max_bytes"] <= 0:
        fail("collect.max_bytes は正の整数")
    if type(collect["credential_redaction"]) is not bool:
        fail("collect.credential_redaction はboolean")
    targets = collect["targets"]
    if not isinstance(targets, dict) or set(targets) != {"channel_messages", "direct_mentions", "group_mentions", "authored_threads"}:
        fail("collect.targets のkeyは channel_messages / direct_mentions / group_mentions / authored_threads")
    if any(type(value) is not bool for value in targets.values()):
        fail("collect.targets の各値はboolean")
    channels = collect["channels"]
    if isinstance(channels, str):
        if channels != "all":
            fail("collect.channels の文字列は all だけを許す")
        if targets["channel_messages"]:
            fail("collect.channels: all では channel_messages: false が必須（全チャンネル全投稿は収集しない）")
    elif isinstance(channels, list):
        if not channels:
            fail("collect.channels は all または1件以上のチャンネルを明示する")
        ids = []
        for item in channels:
            if isinstance(item, str) and ID_RE.match(item):
                ids.append(item)
            elif (isinstance(item, dict) and set(item) <= {"id", "label"} and isinstance(item.get("id"), str)
                  and ID_RE.match(item["id"]) and ("label" not in item or isinstance(item["label"], str))):
                ids.append(item["id"])
            else:
                fail("collect.channels の各要素はチャンネルIDまたは id を持つobject")
        if len(ids) != len(set(ids)):
            fail("collect.channels が重複")
    else:
        fail("collect.channels は all またはチャンネル配列")
    groups = collect["groups"]
    if not isinstance(groups, list) or any(not isinstance(g, dict) or not isinstance(g.get("id"), str) or not ID_RE.match(g["id"]) for g in groups):
        fail("collect.groups の各要素は id を持つobject")
    if len({g["id"] for g in groups}) != len(groups):
        fail("collect.groups のidが重複")
    if targets["group_mentions"] and not groups:
        fail("group_mentions: true では collect.groups を1件以上明示する")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(cfg["timezone"])
    except Exception:
        fail("timezone が不正: {}".format(cfg["timezone"]))
    return cfg


def build_collection_plan(cfg):
    """設定から決定論的にMCP実行計画を組み立てる。同じ設定なら同じ計画になる。"""
    collect = cfg["collect"]
    if collect["channels"] == "all":
        scopes = [{"suffix": "all", "filter": ""}]
    else:
        scopes = [{"suffix": _channel_id(c), "filter": " in:<#{}>".format(_channel_id(c))} for c in collect["channels"]]
    search_ops = []
    if collect["targets"]["direct_mentions"]:
        for scope in scopes:
            search_ops.append({"id": "search-direct-mentions-" + scope["suffix"], "tool": "slack_search_public_and_private",
                               "arguments": {"query": "to:<@{authenticated_user_id}> on:{target_date}" + scope["filter"]},
                               "provides": ["direct_thread_refs_" + scope["suffix"]], "matched": "mention_direct"})
    if collect["targets"]["authored_threads"]:
        for scope in scopes:
            search_ops.append({"id": "search-authored-threads-" + scope["suffix"], "tool": "slack_search_public_and_private",
                               "arguments": {"query": "from:<@{authenticated_user_id}> on:{target_date}" + scope["filter"]},
                               "provides": ["authored_thread_refs_" + scope["suffix"]], "matched": "authored_by_me"})
    if collect["targets"]["group_mentions"]:
        for group in collect["groups"]:
            for scope in scopes:
                search_ops.append({"id": "search-group-mention-{}-{}".format(group["id"], scope["suffix"]), "tool": "slack_search_public_and_private",
                                   "arguments": {"query": '"<!subteam^{}>" on:{{target_date}}'.format(group["id"]) + scope["filter"]},
                                   "provides": ["group_thread_refs_{}_{}".format(group["id"], scope["suffix"])], "matched": "mention_group"})
    operations = [{"id": "compute-target-range", "script": "scripts/date-range.py",
                   "arguments": {"date": "{target_date}", "timezone": cfg["timezone"]},
                   "provides": ["target_start_ts", "target_end_ts"]}]
    if search_ops:
        operations.append({"id": "resolve-authenticated-user", "tool": "slack_read_user_profile", "arguments": {},
                           "provides": ["authenticated_user_id"]})
        operations.extend(search_ops)
        operations.append({"id": "merge-thread-refs", "script": "scripts/merge-thread-refs.py",
                           "arguments": {"input": [op["matched"] + "={result_file:" + op["id"] + "}" for op in search_ops]},
                           "inputs": [name for op in search_ops for name in op["provides"]],
                           "dedupe_by": ["channel_id", "thread_ts"], "merge_field": "matched",
                           "provides": ["merged_thread_refs"]})
        operations.append({"id": "read-matched-threads", "tool": "slack_read_thread", "foreach": "merge-thread-refs.merged_thread_refs",
                           "arguments": {"channel_id": "{item.channel_id}", "message_ts": "{item.thread_ts}"},
                           "bucket_template": "thread-{item.channel_id}-{item.thread_ts_digits}", "provides": ["thread_messages"]})
    if collect["targets"]["channel_messages"]:
        for channel in collect["channels"]:
            cid = _channel_id(channel)
            operations.append({"id": "read-channel-" + cid, "tool": "slack_read_channel",
                               "arguments": {"channel_id": cid, "oldest": "{target_start_ts}", "latest": "{target_end_ts}"},
                               "bucket": cid, "provides": ["channel_messages_" + cid]})
    return {"version": 2,
            "runtime_variables": {"target_date": "{target_date}", "target_start_ts": "{target_start_ts}",
                                  "target_end_ts": "{target_end_ts}", "authenticated_user_id": "{authenticated_user_id}"},
            "operations": operations}


def load_config(raw):
    """<repo>/.harness-plugins/collect-slack.config.yml を直接読み、schemaを検査し、
    slack_dir をrepository root（設定fileの2つ上）基準の絶対pathへ解決し、MCP実行計画を組み立てて返す。"""
    raw = raw.strip()
    if raw.startswith("{"):
        cfg = json.loads(raw)
        if isinstance(cfg, dict) and "collection_plan" in cfg:
            return cfg
        base = os.getcwd()
    else:
        path = Path(raw)
        if path.is_symlink() or not path.is_file():
            fail("設定fileが無い: {}".format(raw))
        cfg = _read_yaml(str(path))
        base = str(path.resolve().parent.parent)
    validate_config(cfg, raw)
    cfg = dict(cfg)
    slack_dir_value = os.path.expanduser(cfg["slack_dir"])
    if not os.path.isabs(slack_dir_value):
        slack_dir_value = os.path.join(base, slack_dir_value)
    cfg["slack_dir"] = os.path.abspath(slack_dir_value)
    cfg["repo_root"] = base
    cfg["collection_plan"] = build_collection_plan(cfg)
    return cfg


def slack_dir(cfg):
    return os.path.abspath(os.path.expanduser(cfg["slack_dir"]))


def index_path(cfg):
    return os.path.join(slack_dir(cfg), "index.jsonl")


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
                required = ['ts', 'source', 'path', 'content_hash', 'target_date', 'bucket']
                if not isinstance(entry, dict) or any(not isinstance(entry.get(key), str) or not entry[key] for key in required):
                    fail("台帳レコードschemaが壊れている。自動で読み飛ばさない")
                if type(entry.get("message_count")) is not int or entry["message_count"] < 0:
                    fail("台帳message_countが壊れている")
                out.append(entry)
            except json.JSONDecodeError:
                fail("台帳に破損したJSON行がある。自動で読み飛ばさない")
    return out


def latest_record(cfg, bucket, target_date):
    found = None
    for rec in read_index(cfg):
        if rec.get("bucket") == bucket and rec.get("target_date") == target_date:
            found = rec
    return found


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def safe_date(d):
    """対象日はディレクトリ名になる。形式を固定してパス脱出を防ぐ。"""
    if not DATE_RE.match(d or ""):
        fail("target-date の形式が不正（YYYY-MM-DD のみ）: {!r}".format(d))
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        fail("target-date が実在しない日付: {!r}".format(d))
    return d


def guard_dir(path):
    return collection_store.guard_dir(path, fail)


def configured_timezone(cfg):
    try:
        return ZoneInfo(cfg["timezone"])
    except (KeyError, ZoneInfoNotFoundError):
        fail("timezone が不正: {!r}".format(cfg.get("timezone")))


def configured_now_iso(cfg):
    return datetime.now(configured_timezone(cfg)).isoformat(timespec="seconds")


def target_epoch_range(target_date, cfg):
    day = datetime.strptime(safe_date(target_date), "%Y-%m-%d").date()
    zone = configured_timezone(cfg)
    return (datetime.combine(day, time.min, zone).timestamp(),
            datetime.combine(day + timedelta(days=1), time.min, zone).timestamp())


def ts_to_configured(ts, cfg):
    try:
        return datetime.fromtimestamp(float(ts), configured_timezone(cfg))
    except (TypeError, ValueError):
        return None


def safe_name(s):
    """bucketを検査する。変換すると別名が衝突するため、不正値は拒否する。"""
    s = (s or "").strip()
    if not s or s in (".", ".."):
        fail("bucket が空、または不正")
    if not re.match(r"^[A-Za-z0-9._@-]+$", s):
        fail("bucket は英数と . _ @ - だけを許す: {!r}".format(s))
    return s


def validate_operation(cfg, operation_id, bucket, thread_ref=""):
    operations = cfg.get("collection_plan", {}).get("operations", [])
    op = next((x for x in operations if x.get("id") == operation_id), None)
    if op is None:
        fail("collection_planに無いoperation-id: {}".format(operation_id))
    if op.get("bucket") is not None:
        if bucket != op["bucket"]:
            fail("operation {} のbucketは {}（受取: {}）".format(operation_id, op["bucket"], bucket))
    elif op.get("bucket_template"):
        try:
            ref = json.loads(thread_ref)
        except (TypeError, ValueError):
            fail("thread保存にはmerge済みの--thread-ref JSONが要る")
        channel_id, thread_ts = ref.get("channel_id"), ref.get("thread_ts")
        if not isinstance(channel_id, str) or not isinstance(thread_ts, str):
            fail("thread-refにchannel_id/thread_tsが無い")
        expected = "thread-{}-{}".format(channel_id, "".join(c for c in thread_ts if c.isdigit()))
        if bucket != expected:
            fail("operation {} のbucketはthread-refから決まる {}（受取: {}）".format(operation_id, expected, bucket))
    else:
        fail("operation {} は保存操作ではない".format(operation_id))
    return op


def yaml_scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def yaml_list(items):
    return "[]" if not items else "[" + ", ".join(yaml_scalar(i) for i in items) + "]"


def build_tags(args, messages):
    """チャンネルと当該リンクを、静的なタグとして持つ。

    あとで「このチャンネルの分だけ」「このスレッドだけ」と束ねるとき、
    本文を読み直さずに front matter だけで判定できるようにする。
    利用者が足したタグはそのまま通す。形は検査しない。
    """
    tags = []
    for t in (args.tags or "").split(","):
        t = t.strip()
        if t:
            tags.append(t)
    if args.bucket:
        tags.append("channel:{}".format(args.bucket))
    if args.label:
        tags.append("channel-name:{}".format(args.label))
    if args.thread_permalink:
        tags.append("link:{}".format(args.thread_permalink))
    elif messages:
        first = (messages[0].get("permalink") or "").strip()
        if first:
            tags.append("link:{}".format(first))
    out, seen = [], set()
    for t in tags:
        if t not in seen:
            seen.add(t); out.append(t)
    return out


def require_permalinks(messages):
    """permalink の無いメッセージを通さない。

    あとから元の発言へ戻れることが収集の目的の半分である。
    リンクが欠けた1件は、その1件だけ検証できない資料になる。
    落ちた件数を黙って報告するのではなく、書き込みごと止める。
    """
    missing = [m.get("ts", "?") for m in messages if not (m.get("permalink") or "").strip()]
    if missing:
        fail("permalink の無いメッセージがある（{}件: {}）。"
             "収集時に必ず取得すること。あとから発言へ戻れない写しは作らない。"
             .format(len(missing), ", ".join(missing[:5])))


def read_messages(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                fail("messages-file に JSON でない行がある")
            if not isinstance(m, dict):
                fail("messages-file の各行はJSON objectに限る")
            if not isinstance(m.get("ts"), str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", m["ts"]):
                fail("messages-file に ts の無いレコードがある")
            if "versions" in m or ("deleted" in m and type(m["deleted"]) is not bool):
                fail("versionsは保存側専用、deletedはbooleanに限る")
            # 並べ替えで float 変換するので、ここで弾く。
            # 後段で落ちると JSON 契約ではなく traceback が出る。
            try:
                float(m["ts"])
            except (TypeError, ValueError):
                fail("ts が数値として解釈できない: {!r}".format(m.get("ts")))
            out.append(m)
    return out


MSG_RE = re.compile(r"^<!--\s*slack-msg\s+(\{.*\})\s*-->$")


def parse_existing(path):
    """既存ファイルから収録済みメッセージを復元する。

    各メッセージの直前に HTML コメントで生の JSON を埋めてあるので、
    再実行時はそれを読んで突き合わせる。本文の見た目に依存しない。
    """
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = MSG_RE.match(line.strip())
            if m:
                try:
                    out.append(json.loads(m.group(1)))
                except json.JSONDecodeError:
                    fail("保存済みmessageが破損している。自動で上書きしない")
    return out


def render(meta, messages, cfg):
    lines = ["---"]
    lines.append("schema: {}".format(SCHEMA))
    lines.append("source: slack")
    for k in ("source_id", "bucket", "label", "url", "target_date"):
        lines.append("{}: {}".format(k, yaml_scalar(meta.get(k))))
    lines.append("fetched_at: {}".format(yaml_scalar(meta["fetched_at"])))
    lines.append("message_count: {}".format(len(messages)))
    # ts は数値に見えるが文字列。素で書くと YAML が float にして精度が落ちる。
    last_ts = meta.get("last_ts")
    lines.append("last_ts: {}".format('"{}"'.format(last_ts) if last_ts else "null"))
    lines.append("content_hash: {}".format(yaml_scalar(meta["content_hash"])))
    lines.append("collector: {}".format(yaml_scalar(COLLECTOR)))
    lines.append("fidelity: markdown-lossy")
    lines.append("omitted: {}".format(yaml_list(meta.get("omitted") or [])))
    # 既知の認証情報フォーマットに機械的に一致し、本文をpermalinkと固定注記へ
    # 差し替えたメッセージが1件でもあれば true。下流（digest等）がこれだけを
    # 見て、原文を読み直さずに機械的検知できるようにする。
    lines.append("redacted: {}".format(yaml_scalar(any(m.get("redacted") for m in messages))))
    # チャンネルと当該リンクは、あとで束ねる手がかりとして静的に持つ。
    # 本文を読み直さなくても、front matter だけで辿れるようにする。
    lines.append("tags: {}".format(yaml_list(meta.get("tags") or [])))
    if meta.get("thread_ts"):
        lines.append("thread_ts: {}".format(yaml_scalar(meta.get("thread_ts"))))
        lines.append("thread_permalink: {}".format(yaml_scalar(meta.get("thread_permalink"))))
    lines.append("---")
    lines.append("")
    lines.append("# {} {}".format(meta.get("label") or meta.get("bucket"), meta.get("target_date")))
    lines.append("")

    for m in messages:
        dt = ts_to_configured(m.get("ts"), cfg)
        hhmm = dt.strftime("%H:%M") if dt else "--:--"
        who = m.get("user_name") or m.get("user") or "unknown"
        tags = []
        if m.get("matched"):
            matched = m["matched"]
            if isinstance(matched, str):
                tags.append(matched)
            elif isinstance(matched, list) and all(isinstance(x, str) for x in matched):
                tags.extend(matched)
            else:
                fail("messages[].matched は文字列または文字列配列")
        if m.get("thread_ts") and m.get("thread_ts") != m.get("ts"):
            tags.append("thread")
        tag = "  `{}`".format(" ".join(tags)) if tags else ""
        link = "  [link]({})".format(m["permalink"]) if m.get("permalink") else ""
        lines.append("<!-- slack-msg {} -->".format(json.dumps(m, ensure_ascii=False, sort_keys=True)))
        lines.append("**{} {}**{}{}".format(hhmm, who, tag, link))
        if m.get("deleted") is True:
            lines.append("[削除通知を受信。収集済み本文を履歴として保持]")
        lines.append("")
        for ln in (m.get("text") or "").splitlines() or [""]:
            lines.append("> {}".format(ln))
        lines.append("")
    return "\n".join(lines)


def cmd_paths(args, cfg):
    args.target_date = safe_date(args.target_date)
    d = slack_dir(cfg)
    print(json.dumps({
        "slack_dir": d,
        "date_dir": os.path.join(d, args.target_date),
        "index": index_path(cfg),
    }, ensure_ascii=False))


def collector_result(decision, reason, artifact=None, counts=None):
    """Collector境界の共通envelope。collect-notesと同じ4キーを返す。"""
    return {"decision": decision, "reason": reason,
            "artifact": artifact or {}, "counts": counts or {}}


def cmd_check(args, cfg):
    root = slack_dir(cfg)
    guard_dir(root)
    with collection_store.locked(root):
        return cmd_check_locked(args, cfg)


def cmd_check_locked(args, cfg):
    args.target_date = safe_date(args.target_date)
    op = validate_operation(cfg, args.operation_id, args.bucket, args.thread_ref)
    rec = latest_record(cfg, args.bucket, args.target_date)
    if rec is None:
        decision, reason = "new", "台帳に無い"
    elif not os.path.exists(rec.get("path") or ""):
        decision, reason = "new", "台帳にはあるが実ファイルが無い（消された）"
    elif args.latest_ts and rec.get("last_ts") != args.latest_ts:
        decision, reason = "updated", "最新 ts が変わった"
    elif not args.latest_ts:
        decision, reason = "recheck", "最新 ts が渡されていないので取得して突き合わせる"
    else:
        decision, reason = "recheck", "追記archive: 各実行で対象日全範囲を再取得して編集を確認する"
    print(json.dumps(collector_result(
        decision, reason,
        {"path": (rec or {}).get("path"), "last_ts": (rec or {}).get("last_ts")},
        {"messages": (rec or {}).get("message_count", 0)}), ensure_ascii=False))


def cmd_append(args, cfg):
    root = slack_dir(cfg)
    guard_dir(root)
    with collection_store.locked(root):
        return cmd_append_locked(args, cfg)


def cmd_append_locked(args, cfg):
    args.target_date = safe_date(args.target_date)
    op = validate_operation(cfg, args.operation_id, args.bucket, args.thread_ref)
    d = slack_dir(cfg)
    guard_dir(d)
    date_dir = os.path.join(d, args.target_date)
    bucket = safe_name(args.bucket)
    path = os.path.join(date_dir, "{}.md".format(bucket))

    incoming = read_messages(args.messages_file)
    require_permalinks(incoming)
    # 既知の認証情報フォーマットに機械的に一致したメッセージは、判断や停止を
    # 挟まずその場で1件だけ本文をpermalink+固定注記へ差し替えて収集を続ける。
    # 利用者に確認を求めない。permalinkはrequire_permalinksで既に必須。
    if cfg.get("collect", {}).get("credential_redaction", True):
        for m in incoming:
            hit = detect_credential(m.get("text") or "")
            if hit:
                m["text"] = REDACTION_NOTE
                m["redacted"] = True
                m["redaction_reason"] = hit
    if op.get("bucket") is not None:
        start_ts, end_ts = target_epoch_range(args.target_date, cfg)
        outside = [m.get("ts") for m in incoming if not (start_ts <= float(m.get("ts", -1)) < end_ts)]
        if outside:
            fail("channel投稿に対象日範囲外のtsがある: {}".format(", ".join(map(str, outside))))
    existing = parse_existing(path)

    by_ts = {m["ts"]: m for m in existing}
    added = 0
    for m in incoming:
        if m["ts"] not in by_ts:
            added += 1
        previous = by_ts.get(m["ts"])
        if previous:
            current = {k: v for k, v in previous.items() if k != "versions"}
            updated = dict(m)
            if m.get("deleted") is True:
                updated = {**current, **m, "text": previous.get("text", "")}
            versions = list(previous.get("versions", []))
            if current != updated and current not in versions:
                versions.append(current)
            if versions:
                updated["versions"] = versions
            m = updated
        by_ts[m["ts"]] = m
    merged = [by_ts[k] for k in sorted(by_ts, key=lambda t: float(t))]
    credential_redacted = sum(1 for m in merged if m.get("redacted"))

    body_seed = json.dumps(merged, ensure_ascii=False, sort_keys=True)
    content_hash = "sha256:" + hashlib.sha256(body_seed.encode("utf-8")).hexdigest()

    rec = latest_record(cfg, args.bucket, args.target_date)
    if rec is not None and rec.get("content_hash") == content_hash and os.path.exists(path):
        print(json.dumps(collector_result(
            "unchanged", "content hashが同じ", {"path": path},
            {"added": 0, "total": len(merged), "credential_redacted": credential_redacted}),
            ensure_ascii=False))
        return

    max_bytes = int(cfg.get("collect", {}).get("max_bytes", 10485760))
    meta = {
        "source_id": "{}@{}".format(args.bucket, args.target_date),
        "bucket": args.bucket,
        "label": args.label or None,
        "url": args.url or None,
        "target_date": args.target_date,
        "fetched_at": configured_now_iso(cfg),
        "last_ts": merged[-1]["ts"] if merged else None,
        "content_hash": content_hash,
        "omitted": [o for o in (args.omitted or "").split(",") if o],
        # チャンネルと当該リンクは必ずタグに入る。指定が無ければ組み立てる。
        "tags": build_tags(args, incoming),
        "thread_ts": args.thread_ts or None,
        "thread_permalink": args.thread_permalink or None,
    }
    out = render(meta, merged, cfg)
    if len(out.encode("utf-8")) > max_bytes:
        fail("出力が上限 {} バイトを超えた。途中で切った写しは作らない。".format(max_bytes))

    entry = {
            "ts": meta["fetched_at"],
            "source": "slack",
            "bucket": args.bucket,
            "label": args.label or None,
            "target_date": args.target_date,
            "last_ts": meta["last_ts"],
            "message_count": len(merged),
            "content_hash": content_hash,
            "redacted": credential_redacted > 0,
            "path": path,
        }
    collection_store.commit(d, {path: out, index_path(cfg): collection_store.append_index(index_path(cfg), entry)})

    print(json.dumps(collector_result(
        "updated" if rec is not None else "written",
        "既存bucketを更新" if rec is not None else "新規bucketを保存",
        {"path": path},
        {"added": added, "total": len(merged), "credential_redacted": credential_redacted}),
        ensure_ascii=False))


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

    sp = sub.add_parser("paths")
    sp.add_argument("--config", required=True)
    sp.add_argument("--target-date", required=True)

    sp = sub.add_parser("check")
    sp.add_argument("--config", required=True)
    sp.add_argument("--operation-id", required=True)
    sp.add_argument("--bucket", required=True)
    sp.add_argument("--target-date", required=True)
    sp.add_argument("--latest-ts", default="")
    sp.add_argument("--thread-ref", default="")

    sp = sub.add_parser("append")
    sp.add_argument("--config", required=True)
    sp.add_argument("--operation-id", required=True)
    sp.add_argument("--bucket", required=True)
    sp.add_argument("--target-date", required=True)
    sp.add_argument("--messages-file", required=True)
    sp.add_argument("--label", default="")
    sp.add_argument("--url", default="")
    sp.add_argument("--omitted", default="")
    sp.add_argument("--tags", default="")
    sp.add_argument("--thread-ts", default="")
    sp.add_argument("--thread-permalink", default="")
    sp.add_argument("--thread-ref", default="")

    sp = sub.add_parser("plan")
    sp.add_argument("--config", required=True)

    args = p.parse_args()
    cfg = load_config(args.config)

    if args.cmd == "plan":
        print(json.dumps({"slack_dir": cfg["slack_dir"], "timezone": cfg["timezone"],
                          "collection_plan": cfg["collection_plan"]}, ensure_ascii=False))
        return
    if args.cmd == "paths":
        run(cmd_paths, args, cfg)
    elif args.cmd == "check":
        run(cmd_check, args, cfg)
    elif args.cmd == "append":
        run(cmd_append, args, cfg)


if __name__ == "__main__":
    main()
