#!/usr/bin/env python3
"""素材を期間で選び、共通形の一覧にして返す。

このスクリプトは**収集プラグインにも資料化プラグインにも依存しない**。
知っているのは「日付ディレクトリの下に front matter 付きの md が並ぶ」という
置き方だけで、それを作ったのが collect-notes でも collect-slack でも
人手でも同じに扱う。

  material.py period --period weekly [--ref YYYY-MM-DD]
      -> {"from": "...", "to": "...", "label": "2026-W33"}

  material.py list --config <json|<repo>/.harness-plugins/digest.config.yml> --digest <name> [--from ...] [--to ...]
      -> {"pipeline": ..., "from": ..., "to": ..., "items": [...], "skipped": [...]}

items の1件は次の形。**資料化側が知るのはこの形だけでよい。**

  {"path", "dir", "date", "source", "source_id", "url", "title",
   "occurred_at", "parts", "bytes"}
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# digest から作れるのは「収集物を状態順に並べ直す」period-digest だけ。
# 制限しないと、収集物からハウツーやコンセプトまで作れる汎用ディスパッチャに戻る。
# 他の型が要るなら write-doc を直接呼ぶ。
ALLOWED_TYPES = ("period-digest",)


def fail(msg, code=2):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(code)


CONFIG_KEYS = ("version", "sources", "labels", "output", "digests")


def validate_config(cfg, path):
    """<repo>/.harness-plugins/digest.config.yml の閉じたschema検査。stepsや型の上書きは受け付けない。"""
    if not isinstance(cfg, dict) or set(cfg) != set(CONFIG_KEYS):
        fail("設定のtop-level keyがschemaと一致しない（version / sources / labels / output / digests）: {}".format(path))
    if type(cfg["version"]) is not int or cfg["version"] != 1:
        fail("versionは1だけを受け付ける")
    if not isinstance(cfg["sources"], list) or any(not isinstance(s, dict) or set(s) != {"dir"} or not isinstance(s["dir"], str) or not s["dir"] for s in cfg["sources"]):
        fail("sources は {dir: <path>} の配列")
    if not isinstance(cfg["labels"], list) or any(not isinstance(l, str) for l in cfg["labels"]):
        fail("labels は文字列の配列")
    output = cfg["output"]
    if not isinstance(output, dict) or set(output) != {"dir", "format"} or not isinstance(output["dir"], str) or not output["dir"] or output["format"] != "markdown":
        fail("output は dir(文字列) と format: markdown だけを持つ")
    if not isinstance(cfg["digests"], list) or not cfg["digests"]:
        fail("digests は1件以上の配列")
    names = []
    for item in cfg["digests"]:
        if not isinstance(item, dict) or set(item) - {"name", "period", "type", "prompt", "labels", "include_parts", "output"}:
            fail("digests の各要素は name / period / type / prompt と任意の labels / include_parts / output だけを持つ")
        if not isinstance(item.get("name"), str) or not item["name"]:
            fail("digests[].name は空でない文字列")
        names.append(item["name"])
        validate(item)
        if "labels" in item and (not isinstance(item["labels"], list) or any(not isinstance(l, str) for l in item["labels"])):
            fail("digests[].labels は文字列の配列")
        if "include_parts" in item and type(item["include_parts"]) is not bool:
            fail("digests[].include_parts はboolean")
        if "output" in item and (not isinstance(item["output"], dict) or set(item["output"]) - {"dir", "format"}):
            fail("digests[].output は dir / format だけを持つ")
    if len(names) != len(set(names)):
        fail("digests[].name が重複")
    return cfg


def load_config(raw):
    """<repo>/.harness-plugins/digest.config.yml を直接読み、schemaを検査し、
    repository root（設定fileの2つ上）を repo_root として返す。JSON文字列も同じschemaで受ける。"""
    raw = raw.strip()
    if raw.startswith("{"):
        cfg = json.loads(raw)
        base = os.getcwd()
    else:
        path = raw
        if os.path.islink(path) or not os.path.isfile(path):
            fail("設定fileが無い: {}".format(path))
        try:
            result = subprocess.run(["yq", "-o=json", "-I=0", ".", path],
                                    capture_output=True, text=True, timeout=10, check=True)
            cfg = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            fail("--config が読めない: {}".format(e))
        base = os.path.dirname(os.path.dirname(os.path.realpath(path)))
    validate_config(cfg, raw)
    cfg = dict(cfg)
    cfg["repo_root"] = base
    return cfg


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(s, what):
    # strptime は 2026-8-14 のような桁落ちも通す。ディレクトリ名と
    # 突き合わせる値なので、桁まで一致していないと拾う先がずれる。
    if not DATE_RE.match(s or ""):
        fail("{} の形式が不正（YYYY-MM-DD のみ）: {!r}".format(what, s))
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        fail("{} の形式が不正（YYYY-MM-DD のみ）: {!r}".format(what, s))


def period_range(period, ref):
    """期間の名前から [from, to] を出す。境界は両端を含む。"""
    if period in ("day", "daily"):
        return ref, ref, ref.isoformat()
    if period in ("week", "weekly"):
        start = ref - timedelta(days=ref.weekday())  # 月曜始まり
        end = start + timedelta(days=6)
        iso = ref.isocalendar()
        return start, end, "{}-W{:02d}".format(iso[0], iso[1])
    if period in ("month", "monthly"):
        start = ref.replace(day=1)
        nxt = (start + timedelta(days=32)).replace(day=1)
        end = nxt - timedelta(days=1)
        return start, end, start.strftime("%Y-%m")
    fail("period が不正: {!r}（daily / weekly / monthly）".format(period))


# front matter は先頭の限られた行数に収まる。ここを超えて探すと、
# 閉じ --- の無いファイルで本文を延々と辞書へ積む（巨大ファイルで RSS が膨らむ）。
FM_MAX_LINES = 200
# front matter の行は「key: value」か、リストの継続だけ。
FM_LINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*\s*:")


def read_front_matter(path):
    """先頭の --- で囲まれた部分だけを読む。

    収集側が出すのは scalar とリテラルのごく狭い形なので、YAML 一般を
    解釈しない。解釈できない値は素通しして、判断は読み手へ渡す。

    **閉じ --- が見つからないファイルは front matter 無しとして扱う。**
    途中で諦めて「そこまでを front matter」にすると、本文の key: value が
    front matter を乗っ取る（title や url を差し替えられる）。
    """
    fm = {}
    try:
        with open(path, encoding="utf-8") as f:
            first = f.readline()
            if first.strip() != "---":
                return None
            for n, line in enumerate(f):
                if n >= FM_MAX_LINES:
                    return None  # 閉じ --- が見つからない＝壊れている
                s = line.rstrip("\n")
                if s.strip() == "---":
                    return fm
                if not s or s.startswith((" ", "\t")):
                    # ネストは親キーの存在だけ拾えれば足りる
                    continue
                # 散文が1行でも混ざっていたら、それは front matter ではない。
                # 閉じ --- を書き忘れたファイルは、本文の途中にある区切り線で
                # 閉じたことにされ、本文の key: value が title や url を乗っ取る。
                # 「key: value でない行が無いこと」を条件にすると、この経路が塞がる。
                if not FM_LINE_RE.match(s):
                    return None
                k, _, v = s.partition(":")
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                # | と > は YAML のリテラルブロックの印であって値ではない。
                # そのまま拾うと title が "|" になる。中身は次行以降の字下げにある。
                if v in ("|", ">", "|-", ">-", "|+", ">+"):
                    v = ""
                fm[k.strip()] = v
    except OSError:
        return None
    return None  # 閉じ --- が無い＝壊れている


def date_dirs(root, dfrom, dto):
    """<root>/<YYYY-MM-DD>/ のうち期間に入るものを返す。"""
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for name in names:
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        try:
            d = datetime.strptime(name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if dfrom <= d <= dto:
            out.append((d, p))
    return out


def gather(source_dirs, dfrom, dto, include_parts):
    items, skipped = [], []
    for spec in source_dirs:
        root = spec["dir"]
        if not os.path.isdir(root):
            # 黙って0件にしない。設定ミスと「その期間に何も無い」は別。
            skipped.append({"path": root, "reason": "置き場が無い"})
            continue
        found_any = False
        for d, ddir in date_dirs(root, dfrom, dto):
            for fn in sorted(os.listdir(ddir)):
                if not fn.endswith(".md"):
                    continue
                path = os.path.join(ddir, fn)
                fm = read_front_matter(path)
                if fm is None:
                    skipped.append({"path": path, "reason": "front matter が無いか閉じていない"})
                    continue
                if "part" in fm and not include_parts:
                    # 文字起こしなど。既定では素材にしない（数万字あるため）
                    skipped.append({"path": path, "reason": "part（{}）".format(fm.get("part"))})
                    continue
                found_any = True
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                # 見出しに使う名前のキーは収集元ごとに違う（議事録は title、
                # Slack はチャンネル名の label）。どれか1つに寄せて渡す。
                # 無ければファイル名。**素材を無題のまま渡さない。**
                title = (fm.get("title") or fm.get("label")
                         or fm.get("bucket") or os.path.splitext(fn)[0])
                items.append({
                    "path": path,
                    "dir": root,
                    "date": d.isoformat(),
                    "source": fm.get("source", ""),
                    "source_id": fm.get("source_id", ""),
                    "url": fm.get("url", ""),
                    "title": title,
                    "occurred_at": fm.get("occurred_at", ""),
                    "parts": "parts" in fm,
                    "bytes": size,
                })
        if not found_any:
            skipped.append({"path": root, "reason": "期間内に日付ディレクトリの素材が無い"})
    items.sort(key=lambda x: (x["date"], x["source"], x["path"]))
    return items, skipped


def resolve_dir(root, p):
    """置き場の相対パスをリポジトリ root 基準で絶対にする。

    設定解決を共有の resolver へ移したので、digest 固有のパス解決はここが持つ。
    cwd 基準にすると、どこから呼んだかで拾う素材が変わる。
    """
    p = os.path.expanduser(p or "")
    return p if os.path.isabs(p) else os.path.join(root, p)


def validate(pl):
    """設定の決定的な部分を検査する。**この検査を落とすと特化が消える。**

    playbook 化で設定解決を共有の resolver へ移したとき、ここの検査ごと
    消えていた。型の制限は digest の中心なので、設定を読む側が必ず持つ。
    """
    name = pl.get("name") or "?"
    t = pl.get("type") or ""
    if not t:
        fail("digest '{}' に type が無い（必須。既定へは倒さない）。使えるのは: {}"
             .format(name, " / ".join(ALLOWED_TYPES)))
    if t not in ALLOWED_TYPES:
        fail("digest '{}' の type が使えない: {}。digest から使えるのは {} のみ。"
             "他の型が要るなら write-doc を直接呼ぶこと。"
             .format(name, t, " / ".join(ALLOWED_TYPES)))
    pr = pl.get("period", "weekly")
    if pr not in ("day", "daily", "week", "weekly", "month", "monthly"):
        fail("digest '{}' の period が不正: {}（daily / weekly / monthly）".format(name, pr))
    if not isinstance(pl.get("prompt"), str):
        fail("digest '{}' の prompt は文字列で指定すること".format(name))
    return pl


def find_digest(cfg, name):
    pls = cfg.get("digests") or []
    if not pls:
        fail("設定に digests が無い")
    if not name:
        if len(pls) == 1:
            return pls[0]
        fail("digest を指定すること（候補: {}）".format(
            ", ".join(p.get("name", "?") for p in pls)))
    for p in pls:
        if p.get("name") == name:
            return p
    fail("そんな digest は無い: {}（候補: {}）".format(
        name, ", ".join(p.get("name", "?") for p in pls)))


def cmd_period(args):
    ref = parse_date(args.ref, "--ref") if args.ref else datetime.now(JST).date()
    dfrom, dto, label = period_range(args.period, ref)
    print(json.dumps({"from": dfrom.isoformat(), "to": dto.isoformat(),
                      "label": label, "ref": ref.isoformat()}, ensure_ascii=False))


def cmd_list(args):
    cfg = load_config(args.config)
    pl = validate(find_digest(cfg, args.digest_name))

    root = cfg.get("repo_root") or os.getcwd()
    source_dirs = cfg.get("sources") or []
    dirs = [dict(d, dir=resolve_dir(root, d.get("dir"))) for d in source_dirs]
    if not dirs:
        fail("設定の sources が空（digest '{}' の対象directoryを1件以上指定すること）"
             .format(pl.get("name")))

    ref = parse_date(args.ref, "--ref") if args.ref else datetime.now(JST).date()
    if args.date_from or args.date_to:
        if not (args.date_from and args.date_to):
            fail("--from と --to は両方指定すること")
        dfrom = parse_date(args.date_from, "--from")
        dto = parse_date(args.date_to, "--to")
        # 明示した期間が、その digest の period とちょうど一致するなら
        # 期間名（2026-W33 など）を使う。ファイル名が二重にならないようにする。
        pf, pt, plabel = period_range(pl.get("period", "weekly"), dfrom)
        if (pf, pt) == (dfrom, dto):
            label = plabel
        else:
            label = "{}_{}".format(dfrom.isoformat(), dto.isoformat())
    else:
        dfrom, dto, label = period_range(pl.get("period", "weekly"), ref)
    if dfrom > dto:
        fail("--from が --to より後になっている")

    items, skipped = gather(dirs, dfrom, dto, bool(pl.get("include_parts")))

    # type と出力設定は resolver が検査済みのものを載せるだけ。
    # ここでは判断しない。
    print(json.dumps({
        "digest": pl.get("name"),
        "from": dfrom.isoformat(),
        "to": dto.isoformat(),
        "label": label,
        "count": len(items),
        "items": items,
        "skipped": skipped,
        "type": pl.get("type") or "",
        "output": pl.get("output") or {},
        "prompt": pl.get("prompt"),
    }, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("period")
    sp.add_argument("--period", required=True)
    sp.add_argument("--ref", default="")

    sp = sub.add_parser("list")
    sp.add_argument("--config", required=True)
    sp.add_argument("--digest", dest="digest_name", default="")
    sp.add_argument("--from", dest="date_from", default="")
    sp.add_argument("--to", dest="date_to", default="")
    sp.add_argument("--ref", default="")

    args = p.parse_args()
    if args.cmd == "period":
        cmd_period(args)
    elif args.cmd == "list":
        cmd_list(args)


if __name__ == "__main__":
    main()
