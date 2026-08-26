# Collection

会議、Slack、agent sessionを収集し、期間digestを作るClaude Code/Codex両対応marketplaceである。資料化に`write-doc@write-doc`、session本文の規律に`writing-rules@write-doc`を使う。

```bash
codex plugin marketplace add nakamori-naoya/collection
codex plugin add meeting-collect@collection
codex plugin add slack-collect@collection
codex plugin add digest@collection
```

検証は`bash scripts/validate.sh`で実行する。
