# Collection

会議、Slack、agent sessionを収集し、期間digestを作るClaude Code/Codex両対応marketplaceである。

## インストール済みである必要があるplugin

- `digest@collection`: `write-doc@write-doc`
- `session-digest@collection`: `session-collect@collection`、`writing-rules@write-doc`
- `meeting-collect@collection`: 追加依存なし
- `session-collect@collection`: 追加依存なし
- `slack-collect@collection`: 追加依存なし

## 検証

```bash
bash scripts/validate.sh
```
