---
name: collect-sessions
description: Claude Code / Codexのローカルセッションを、原文を複製せず対象日に活動したセッションの非公開索引として収集する。「セッションを集めて」「今日のCodex作業を記録して」「collect-sessions」と依頼されたときに使う。
---

# collect-sessions

対象日に活動したClaude Code / Codexセッションを発見し、正本への参照と決定的メタデータだけを非公開の `state_dir` へ保存する。原文、プロンプト、応答、tool入出力、system promptは複製しない。要約は別の仕事である。

## 入力

- 対象日: 利用者の指定が無ければ設定の `timezone` での当日。対象日はセッション開始日ではなく、その日にtimestampを持つイベントが存在するかの検索条件である。
- 設定file: `${XDG_CONFIG_HOME:-~/.config}/harness-plugins/collect-sessions.config.yml`。利用者ごとの1層で必須、同梱既定へのfallbackは無い。セッション置き場と索引はmachine固有なので、repositoryではなく利用者の設定に置く。keyは `version: 1`、`state_dir`（絶対path。`~` 展開可）、`timezone`、`sources.claude_code.{enabled, root}`、`sources.codex.{enabled, root}`、`collection.{include_subagents, max_scan_files, max_source_bytes, stable_read_retries, quiescent_after_minutes}`。記入例は [`assets/collect-sessions.config.example.yml`](assets/collect-sessions.config.example.yml)。fileが無い、keyが足りない・余る、型や値が許容範囲外、相対path、有効なsourceが無いなら `session.py` が診断を返して止まる。

## 判断基準

- **停止条件か、スキップか。** enabledなrootの欠落、中間の真にparse不能なJSONL、上限超過、索引破損、保存先の安全違反は止まる。末尾の書きかけだけは `provisional` として扱う。対象schema外のfile（sessionIdを持たないWorkflow journal.jsonlなど）や、sessionIdはあるが有効なturn / timestampをまだ持たない空セッションは止まらず、1件だけ理由付きでスキップして走査を続ける（`counts.unrecognized`、私的な `artifact.skipped_log`）。
- **原文を写していないか。** 索引に入るのは正本への参照と決定的メタデータだけである。形式、privacy、更新規則は[セッション形式と収集契約](references/workflow.md)に従う。
- **0件でも報告するか。** 0件でも `counts` を明示し、黙って終わらない。

## 手順

1. **対象日を決める。** 指定が無ければ設定の `timezone` の当日。
2. **走査する。** `python3 scripts/session.py scan --config <設定file> --date <YYYY-MM-DD>` を実行する。事前確認だけなら `--dry-run` を付ける。入力は設定fileの絶対pathと対象日、出力は `decision / reason / artifact / counts` の4キーを持つ標準出力のJSON、終了codeは `0` = 走査した、`2` = 設定file不在・schema違反・停止条件（診断は標準出力のJSON `error`）。`2` なら止まる。
3. **報告する。** 対象日、`counts`（discovered / written / updated / unchanged / skipped / unrecognized / provisional）、`artifact` の日次索引、`provisional` の有無を報告する。

## 停止条件

止まるのは次の場合である。索引を更新したことにせず、診断または `reason` を報告する。

- 設定fileが無い、schema に合わない、有効なsourceが無い。
- `session.py scan` が `2` を返した（enabledなrootの欠落、中間のparse不能なJSONL、上限超過、索引破損、保存先の安全違反）。

次は止まらず、記録して進む。

- 対象schema外のfileや、有効なturn / timestampをまだ持たない空セッションがある。1件だけ理由付きでスキップして走査を続け、`counts.unrecognized` に数える。
- 末尾が書きかけのセッションがある。`provisional` として索引に載せ、報告に明記する。
- 対象日の指定が無い。設定の `timezone` の当日を対象日として進め、報告に明記する。

## 出力

`state_dir` 内の日付別索引（非公開）と、手順3の報告。
