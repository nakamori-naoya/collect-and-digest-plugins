#!/usr/bin/env python3
"""資料の末尾へ載せる静的情報を作り、後から読み直す。

資料を1本ずつ読ませずに「このラベルの資料だけ集める」をやるには、
**資料自身が機械で読める形の情報を持っている**必要がある。
別に台帳を持つと資料と台帳がずれるので、正本は資料の中に置く。

  doc-meta.py skeleton --config <json|path> --digest <name> [--from --to] [--ref]
      -> 資料へ載せる情報の骨格（参加者だけ空。書き手が埋める）

  （媒体へ写すのは doc-render の render-meta.py。ここは中身だけを扱う）

  doc-meta.py index <dir> [--recursive]
      -> ディレクトリ内の資料から情報を抜き出して JSONL

  doc-meta.py group <dir> --by <ラベルのキー>
      -> ラベルで束ねた一覧

ラベルは自由に付けてよい。`key:value` の形にしておくと group --by で束ねられる。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
BEGIN = "doc-meta:begin"
END = "doc-meta:end"


def fail(msg, code=2):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(code)


def load_json(raw):
    raw = (raw or "").strip()
    if raw.startswith("{"):
        return json.loads(raw)
    try:
        result = subprocess.run(["yq", "-o=json", "-I=0", ".", raw],
                                capture_output=True, text=True, timeout=10, check=True)
        cfg = json.loads(result.stdout)
        return cfg.get("playbook", cfg)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        fail("読めない: {}".format(e))


def norm_labels(items):
    """空白を落とし、空を捨て、順序を保ったまま重複を除く。

    中身は検査しない。利用者が自由に決めるものなので、形を強制すると
    「使える語彙」を機械が決めることになる。
    """
    out, seen = [], set()
    for x in items or []:
        s = str(x).strip()
        if not s or "\n" in s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def cmd_skeleton(args):
    cfg = load_json(args.config)
    target = None
    for d in cfg.get("digests") or []:
        if d.get("name") == args.digest_name:
            target = d
            break
    if target is None:
        fail("そんな digest は無い: {}".format(args.digest_name))

    labels = norm_labels((cfg.get("labels") or []) + (target.get("labels") or []))
    # 自動で付くラベル。設定を書かなくても束ねられる最低限。
    auto = ["digest:{}".format(target.get("name", "")),
            "type:{}".format(target.get("type", ""))]
    if args.label:
        auto.append("period:{}".format(args.label))
    for s in cfg.get("sources") or []:
        d = s.get("dir") or ""
        if d:
            auto.append("source:{}".format(os.path.basename(d.rstrip("/"))))

    meta = {
        "schema": 1,
        "producer": target.get("name"),
        "digest": target.get("name"),
        "type": target.get("type"),
        "period": {"from": args.date_from, "to": args.date_to, "label": args.label},
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        # 参加者は素材の本文からしか分からない。書き手が埋める。
        # 分からないものを空配列のまま残すと「参加者ゼロ」と読まれるので、
        # 埋められなければ participants_note に理由を書く。
        "participants": [],
        "participants_note": "",
        "labels": norm_labels(labels + auto),
        "materials": args.materials and json.loads(args.materials) or [],
    }
    print(json.dumps(meta, ensure_ascii=False))


# 本文が印そのものに言及していると、最初の一致が壊れた JSON になって
# 索引から丸ごと消える。**候補を1つで諦めず、解釈できるものを探す。**
META_RE = re.compile(r"<!--\s*" + re.escape(BEGIN) + r"\s*-->(.*?)<!--\s*" + re.escape(END) + r"\s*-->", re.S)
META_MD_RE = re.compile(r"<!--\s*" + re.escape(BEGIN) + r"(.*?)" + re.escape(END) + r"\s*-->", re.S)


def extract_meta(path):
    try:
        with open(path, encoding="utf-8") as f:
            s = f.read()
    except OSError:
        return None
    for rx in (META_RE, META_MD_RE):
        for mm in rx.finditer(s):
            body = re.sub(r"</?script[^>]*>", "", mm.group(1)).strip()
            try:
                return json.loads(body)
            except ValueError:
                continue  # この候補は壊れている。次を探す
    return None


def walk_docs(root, recursive):
    if not os.path.isdir(root):
        fail("ディレクトリが無い: {}".format(root))
    if recursive:
        for dp, _, fns in os.walk(root):
            for fn in sorted(fns):
                if fn.endswith((".html", ".md")):
                    yield os.path.join(dp, fn)
    else:
        for fn in sorted(os.listdir(root)):
            if fn.endswith((".html", ".md")):
                yield os.path.join(root, fn)


def cmd_index(args):
    found = 0
    unindexed = []
    for path in walk_docs(args.dir, args.recursive):
        m = extract_meta(path)
        if m is None:
            # 索引に載らなかった資料を黙って落とすと、「全部載っている」と
            # 読まれる。何件を、どういう理由で落としたかを出す。
            unindexed.append(path)
            continue
        # 絶対パスはマシン固有で、資料を渡した相手には意味が無い。
        # 索引を作った側の手元で分かればよいので、置き場からの相対にする。
        try:
            m["path"] = os.path.relpath(path, args.dir)
        except ValueError:
            m["path"] = os.path.basename(path)
        print(json.dumps(m, ensure_ascii=False))
        found += 1
    if unindexed:
        print(json.dumps({"warning": "静的情報を持たないため索引に載せなかった資料がある",
                          "count": len(unindexed),
                          "paths": [os.path.basename(x) for x in unindexed[:20]]},
                         ensure_ascii=False), file=sys.stderr)
    if found == 0:
        # 黙って空にしない。情報を持たない資料しか無いのか、置き場が違うのか。
        print(json.dumps({"warning": "doc-meta を持つ資料が無い", "dir": args.dir},
                         ensure_ascii=False), file=sys.stderr)


def entry(root, path, m):
    """束ねた一覧の1件。

    --recursive では別のディレクトリに同名の資料が並ぶ。
    ファイル名だけを返すと、どちらのことか分からなくなる。
    置き場からの相対にすれば、機械固有のパスを出さずに区別できる。
    """
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        rel = os.path.basename(path)
    return {"path": rel, "label": (m.get("period") or {}).get("label", ""),
            "producer": m.get("producer") or m.get("digest"), "type": m.get("type")}


def cmd_group(args):
    key = args.by
    buckets = {}
    for path in walk_docs(args.dir, args.recursive):
        m = extract_meta(path)
        if m is None:
            continue
        hit = False
        for lb in m.get("labels") or []:
            if lb == key:
                bucket = lb
            elif lb.startswith(key + ":"):
                bucket = lb[len(key) + 1:]
            else:
                continue
            hit = True
            buckets.setdefault(bucket, []).append(entry(args.dir, path, m))
        if not hit:
            buckets.setdefault("(ラベルなし)", []).append(entry(args.dir, path, m))
    print(json.dumps({"by": key, "groups": buckets}, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("skeleton")
    sp.add_argument("--config", required=True)
    sp.add_argument("--digest", dest="digest_name", required=True)
    sp.add_argument("--from", dest="date_from", default="")
    sp.add_argument("--to", dest="date_to", default="")
    sp.add_argument("--label", default="")
    sp.add_argument("--materials", default="")


    sp = sub.add_parser("index")
    sp.add_argument("dir")
    sp.add_argument("--recursive", action="store_true")

    sp = sub.add_parser("group")
    sp.add_argument("dir")
    sp.add_argument("--by", required=True)
    sp.add_argument("--recursive", action="store_true")

    args = p.parse_args()
    {"skeleton": cmd_skeleton, "index": cmd_index, "group": cmd_group}[args.cmd](args)


if __name__ == "__main__":
    main()
