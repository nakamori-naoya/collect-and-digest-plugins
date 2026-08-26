#!/usr/bin/env python3
"""Slack検索結果のthread参照を決定的に統合する。

入力はJSON配列を持つ複数ファイル。channel_id + thread_tsで重複排除し、
matchedだけを出現順に和集合化したJSON配列をstdoutへ出す。
"""
import argparse
import json
import re
import sys


def fail(message):
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(2)


p = argparse.ArgumentParser()
p.add_argument("--input", action="append", required=True,
               help="matched=path（例: mention_direct=result.json）")
args = p.parse_args()
merged = {}
order = []
for spec in args.input:
    if "=" not in spec:
        fail("--input は matched=path: {}".format(spec))
    input_matched, path = spec.split("=", 1)
    if not input_matched or not path:
        fail("--input は matched=path: {}".format(spec))
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, ValueError) as exc:
        fail("入力を読めない: {} ({})".format(path, exc))
    if not isinstance(rows, list):
        fail("入力はJSON配列: {}".format(path))
    for row in rows:
        if not isinstance(row, dict):
            fail("thread参照はobject: {}".format(path))
        channel_id = row.get("channel_id")
        thread_ts = row.get("thread_ts") or row.get("ts")
        if (not isinstance(channel_id, str) or
                not re.match(r"^[A-Za-z0-9._-]+$", channel_id) or
                not isinstance(thread_ts, str) or
                not re.match(r"^[0-9]+(?:\.[0-9]+)?$", thread_ts)):
            fail("channel_id/thread_tsが無い: {}".format(path))
        key = (channel_id, thread_ts)
        matched = row.get("matched", input_matched)
        if isinstance(matched, str):
            matched = [matched]
        if not isinstance(matched, list) or not all(isinstance(x, str) and x for x in matched):
            fail("matchedは文字列または文字列配列: {}".format(path))
        if key not in merged:
            merged[key] = dict(row)
            merged[key]["thread_ts"] = thread_ts
            merged[key]["thread_ts_digits"] = "".join(c for c in thread_ts if c.isdigit())
            merged[key]["matched"] = []
            order.append(key)
        for value in matched:
            if value not in merged[key]["matched"]:
                merged[key]["matched"].append(value)
print(json.dumps([merged[key] for key in order], ensure_ascii=False))
