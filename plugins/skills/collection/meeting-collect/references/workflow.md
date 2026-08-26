# 議事録収集工程の詳細

## 対象日の判定

1. `occurred_at` を`${.timezone}`へ直した日付を使う。
2. 取れない場合だけ、上流の作成日時を`${.timezone}`へ直して代替する。

## checkの結果

| decision | 動作 |
|---|---|
| `new` | 本文を取得して書く |
| `updated` | 本文を取得して書き直す |
| `unchanged` | 何もしない |
| `recheck` | 本文を取得してhashで判定する |

## write

本文は原文Markdownのまま一時ファイルへ書く。front matterは自作しない。

```bash
python3 "${PLUGIN_ROOT}/scripts/note.py" write --config "$CFG_FILE" \
  --source notion --source-id <ID> --url <URL> --title <会議名> \
  --target-date <YYYY-MM-DD> --body-file /tmp/body.md \
  --occurred-at <ISO8601> --attendees "a@example.com,b@example.com" \
  --source-updated-at <ISO8601> --omitted "comments,images,child_pages" \
  [--recording-url <URL>] [--transcript-file /tmp/transcript.md] [--props <JSON>]
```

## 報告

対象日、新規・更新・変更なしの件数とタイトル、スキップ理由、保存先を報告する。

## 規律

- 本文、日時、参加者、録画URL、DBプロパティを取れる範囲で保存する。推定しない。
- 文字起こしは既定ON。コメント・添付・画像は既定OFF、子ページはリンクだけ残す。
- 要約、伏せ字、truncationをしない。上限超過は部分保存せず停止する。
- `fidelity: markdown-lossy` と省略項目を記録する。
- git管理下への保存は拒否する。
