# collect-slack — 2026-09-16 実行記録の所見

記録: [collect-slack.json](collect-slack.json)（case `collect-and-digest-plugins-contract`、stage `after-plan-and-required-reference-read`、resources `references/targets.md` / `references/workflow.md`、生成 `claude-opus-5` effort high、独立judge `claude-sonnet-5`、SKILL sha256 `db25618d14f5…` ＝ 確定版）。[attempt-1](collect-slack.attempt-1.json) は確定前のSKILL（`f1cb1a5b…`）に対する有効な記録。

## 実行

```bash
cd collect-and-digest-plugins && python3 scripts/evaluate-skills.py --fixtures evals/scenarios.json \
  --model-command '["python3","scripts/claude-eval-adapter.py"]' --judge-command '["python3","scripts/claude-eval-adapter.py"]' \
  --model claude-opus-5 --judge-model claude-sonnet-5 --settings '{"effort":"high"}' --output evals/runs/2026-09-16/collect-slack.json
```

fixtureの文言は旧runtimeの `prepare` から現行の `scripts/message.py plan` へ追従させた（criteriaは不変）。

## agentの所見（「」は応答の逐語）

| criterion | 所見 | 根拠 |
|---|---|---|
| archive | 満たす。同ts編集は新本文だけをJSONLに書きscriptが旧本文を `versions` へ退避、明示削除は `deleted: true` のtombstoneで本文保持、取得結果に無い発言は書かない | 「旧本文「議題A」は書かない」「tombstone（`deleted=true`）になり、保存済み本文はそのまま残る」「入力に無いだけなので保持される。削除とは推定しない」 |
| scope | 満たす。対象日範囲外のtsを持つレコードは編集・削除通知であってもJSONLに入れない | 「範囲外のレコードは編集・削除通知であっても今回のJSONLには含めない」 |
| fidelity | 満たす。fixtureの本文だけを使い、3つのscript呼び出しは未実行と明示 | 「fixtureで与えられた本文だけを使い」「実行順（未実行、呼び出しを明示）」 |
| configured-timezone | 満たす。Asia/Tokyoの00:00〜翌00:00で境界を決め、epoch秒の手計算（1788534000 / 1788620400）も正しい | 「境界は設定timezoneで決め、端末のUTCは使わない。」 |

judge（4件pass）と一致。

## 気づき

- attempt-1にあった、`check` が `unchanged` でも同ts編集・削除は最新tsで検出できないという指摘は、本記録でも「`unchanged` でも、fixtureには同ts編集と明示削除があるため、それらは追記として `append` に渡す」として残っている。`message.py check` の判定契約が編集・削除を取りこぼす可能性の材料（未確認。collect-and-digest担当へ）。
- attempt-1の末尾にあった許可待ちの文はこの記録には無い。

## 未確認

- 実Slack MCP・実 `message.py` の実行は行っていない。
