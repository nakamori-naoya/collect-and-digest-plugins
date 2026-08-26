# session-collect — 設定リファレンス

Claude Code / Codexのローカルセッションを、原文を複製せず日付別の非公開索引として収集する。要約はしない。

設定は`scope > local > repository > personal > bundled defaults`から最上位の1ファイルだけを選び、マージしない。

```yaml
version: 1
state_dir: ~/.local/state/harness-plugins/session-collect
timezone: Asia/Tokyo
sources:
  claude_code: {enabled: true, root: ~/.claude/projects}
  codex: {enabled: true, root: ~/.codex/sessions}
collection:
  include_subagents: true
  max_scan_files: 5000
  max_source_bytes: 52428800
  stable_read_retries: 3
  quiescent_after_minutes: 30
instructions:
  collection:
    directive: セッション原文を複製せず、決定的メタデータと正本への非公開参照だけを日付別索引へ記録する
```

`state_dir`はrepository外の非公開directoryを推奨する。ネイティブIDは保存先固有saltで不透明化される。enabledなsource rootが無い場合、索引破損、ファイル上限超過、真にparse不能なJSONLでは停止する。セッションファイルが対象schema外（sessionId自体を持たないWorkflow journal形式など）や、sessionIdはあるが有効なturn/timestampをまだ持たない空セッションは、理由付きで`state_dir/skipped.jsonl`へ記録してスキャンを継続する（`counts.unrecognized`で件数を示す）。

```bash
python3 scripts/session.py scan --config <解決済みYAML> --date 2026-08-16 --dry-run
```

通常実行では単一正本`state_dir/index.jsonl`をatomicに更新する。各レコードの`activity_dates`で日付を引き、セッション原文は保存しない。
