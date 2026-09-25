# 議事録の保存

本文は原文Markdownのまま一時fileへ書き、front matterは自作しない。

```bash
python3 scripts/note.py write --config "$CONFIG" \
  --source notion --source-id <ID> --url <URL> --title <会議名> \
  --target-date <YYYY-MM-DD> --body-file /tmp/body.md \
  --occurred-at <ISO8601> --attendees "a@example.com,b@example.com" \
  --source-updated-at <ISO8601> --omitted "comments,images,child_pages" \
  [--recording-url <URL>] [--transcript-file /tmp/transcript.md] [--props <JSON>]
```

文字起こしは既定で取る。コメント、添付、画像は既定で取らず、子ページはリンクだけ残す。`fidelity: markdown-lossy` と省いた項目を記録する。保存先はgit管理下に置かない。

更新は本文と全metadataのhashで判断し、`source_updated_at` だけの更新も台帳とfront matterへ反映する。対象日が変わったときは旧日の主文書と文字起こしを履歴として残し、台帳の最新のpathを今の文書として扱う。
