---
name: collect-slack
description: 設定timezone上の対象日（既定は今日）のSlackを集めて保存する。repositoryの設定fileから組み立てたMCP実行計画に従い、全チャンネルまたは明示した複数チャンネルから、直接メンション・グループメンション・本人発言・通常投稿を明示的に選んで取る。要約も抽出もしない。「Slackを集めて」「今日のSlackを取り込んで」と言われたときに使う。
---

# collect-slack

対象日に属するSlackの発言を、原文のまま `slack_dir/<対象日>/` へ落とす。正本は常にSlackであり、ここに置くのはその写しで、Slackへ書き戻す動線は作らない。抽出、要約、意味的な伏せ字はしない。例外は一つだけで、既知の認証情報フォーマット（PEM秘密鍵、GCPサービスアカウントJSON、AWS Access Key IDなど）に機械的に一致したメッセージは、`collect.credential_redaction` が `true` のときその場で本文を `permalink` と固定注記へ差し替えて収集を続ける（[保存工程](references/workflow.md)）。

## 入力

- 対象日: 利用者が `--date 2026-08-12` のように指定した日。指定が無ければ設定の `timezone` での当日。directoryのキーは対象日であって起動日ではない。
- 設定file: `<repository root>/.harness-plugins/collect-slack.config.yml`。1層で必須、同梱既定へのfallbackは無い。keyは `version: 1`、`slack_dir`（相対ならrepository root基準）、`timezone`、`collect.channels`（`all` またはチャンネルの配列）、`collect.targets.{channel_messages, direct_mentions, group_mentions, authored_threads}`（boolean）、`collect.groups`（`id` を持つobjectの配列）、`collect.max_bytes`、`collect.credential_redaction`。記入例は [`assets/collect-slack.config.example.yml`](assets/collect-slack.config.example.yml)。fileが無い、keyが足りない・余る、型や値が許容範囲外なら `message.py` が診断を返して止まる。

## 判断基準

- **計画にある操作か。** 実行するMCP操作は `scripts/message.py plan` が設定から組み立てた `collection_plan.operations` だけである。計画に無い操作を足さず、削らず、並べ替えない。
- **取る前に判定したか。** バケットごとに `message.py check` の `decision` を見る。`new` / `updated` は本文を取得して書く、`unchanged` は何もしない、`recheck` は最新tsの一致に関係なく対象日全範囲を再取得して編集を突き合わせる。
- **MCPが使えない対象か。** MCP未接続・権限不足はその操作だけをスキップして理由を記録し、収集全体を止めない。
- **0件でも報告するか。** 0件は「0件だった」と報告し、黙って終わらない。

## 手順

1. **設定とMCP実行計画を読む。** `python3 scripts/message.py plan --config <設定file>` を実行する。入力は設定fileの絶対path、出力は `slack_dir`（絶対path）、`timezone`、`collection_plan` を持つ標準出力のJSON、終了codeは `0` = 計画を返した、`2` = 設定file不在または schema 違反（診断は標準出力のJSON `error`）。`2` なら止まる。
2. **対象日を決める。** 指定が無ければ `timezone` の当日を使う。
3. **計画を配列順に実行する。** `{target_date}`、`{target_start_ts}`、`{target_end_ts}` を対象日から確定し（`scripts/date-range.py --date <YYYY-MM-DD> --timezone <timezone>`。標準出力のJSONで開始・終了tsを返す）、本人解決の出力で `{authenticated_user_id}` を置換する。`inputs` は指定された出力を合流し、`foreach` はproducer付き参照の1件ごとに実行する。ツールと引数の意味は[対象別の収集方法](references/targets.md)に従う。
4. **取る前に判定する。** `python3 scripts/message.py check --config <設定file> --operation-id <planのoperation.id> --bucket <planのbucket> --target-date <YYYY-MM-DD> --latest-ts <そのバケットの最新ts>` を実行する。出力は `decision` を持つ標準出力のJSON、終了codeは `0` = 判定した、`2` = 引数・設定・計画にないoperationの不備。
5. **書き込む。** 取得した発言を1行1 JSONの一時fileへ書き、[保存工程](references/workflow.md)の `message.py append` へ渡す。scriptが重複排除、整列、front matter、台帳更新を行う。終了codeは `0` = 保存した、`2` = 不備（診断は標準出力のJSON `error`）。`2` ならそのバケットの保存を成功扱いにしない。
6. **報告する。** 対象日、バケットごとの新規追加 / 総数、`credential_redacted` の合算件数、スキップした対象と理由（MCP未接続、権限なし、設定で無効）、保存先 `slack_dir/<対象日>/` を報告する。

保存契約は追記archiveである。各収集実行で指定対象日の全範囲を再取得し、スレッドは取得可能な全返信を再取得する。指定していない過去日は自動更新しない。同じtsの編集は `versions` へ旧本文を保持し、明示的な削除通知だけ `deleted=true` として収集済み本文を残す。取得結果に無いことを削除と推定しない。本文・台帳は保存directory全体を排他し、途中中断は次回の check / append でjournalを再適用してから処理する。

## 停止条件

止まるのは次の場合である。診断を報告し、保存済みと主張しない。

- 設定fileが無い、または schema に合わない（`message.py plan` が `2`）。
- `message.py check` / `append` が `2` を返した。そのバケットを保存済みとして扱わない。

次は止まらず、記録して進む。

- MCP未接続・権限不足で取れない対象がある。その操作だけをスキップし、理由を報告に残して残りを続ける。
- 対象日の指定が無い。設定の `timezone` の当日を対象日として進め、報告に対象日を明記する。
- 取得結果に無いレコードがある。削除と推定せず保持し、APIが返さない編集・削除は反映できないことを報告に書く。

## 出力

保存先 `slack_dir/<対象日>/` の写しと台帳の更新。報告は手順6の項目を持つ。
