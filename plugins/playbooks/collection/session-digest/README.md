# session-digest — 設定リファレンス

`session-collect`の非公開索引から、対象日に活動したセッションごとの短い要約を日次Markdownへ保存するplaybook。セッション原文は保存しない。

必要なプラグインは`session-collect@collect-and-digest`と`writing-rules@write-doc`。versionは固定せず、解決先のmanifest identityと必要なskillを検査する。どちらかが欠けていれば停止する。

```yaml
output:
  dir: ~/agent-session-digests
  format: markdown
  timezone: Asia/Tokyo
  max_chars_per_session: 400
  subagents: exclude
```

日次資料は成果・変更対象・判断・却下案・検証・未解決事項・次の行動を持つ。front matterには不透明session参照、収集時刻、生成モデル、prompt契約、検証状態、人間確認状態、横断集約用タグを保存する。タグは利用者が明示した公開可能なaliasだけを使う。絶対path、ネイティブID、tool入出力、system prompt、repository URLは載せない。入力hashが変わった既存資料は、明示的なforceなしに上書きしない。
