---
name: collect-slack
description: 設定timezone上の対象日（既定は今日）のSlackを集めて保存する。repositoryの設定fileから組み立てたMCP実行計画に従い、全チャンネルまたは明示した複数チャンネルから、直接メンション・グループメンション・本人発言・通常投稿を明示的に選んで取る。要約も抽出もしない。「Slackを集めて」「今日のSlackを取り込んで」と言われたときに使う。
---

# collect-slack

対象日に属するSlackの発言を、原文のまま `slack_dir/<対象日>/` へ写す。元の記録は常にSlackにあり、ここに置くのはその写しである。

## Slackは読むだけにする

この入口はSlackを読むだけで、送信、リアクション、canvasやlistの更新のような書き込みの tool は使わない。写しを作る仕事で、利用者の許可なく他人の目に触れる場所を変えないためである。写すだけにし、抽出、要約、意味で判断した伏せ字はしない。例外は、既知の認証情報の形（PEM秘密鍵、GCPサービスアカウントJSON、AWS Access Key IDなど）に機械的に一致した発言だけで、`collect.credential_redaction` が `true` なら `message.py append` がその本文を差し替える（[保存工程](references/workflow.md)）。

## 取る範囲は設定が決め、黙って変えない

実行するMCP操作は、`scripts/message.py plan` が設定から組み立てた `collection_plan.operations` だけである。計画に無い操作を足さず、削らず、並べ替えない。チャンネルIDが分からなければ `slack_search_channels` で解決し、推測で作らない。計画の tool が使えず、狭い範囲の tool で代えたとき（たとえば `slack_search_public_and_private` の代わりに `slack_search_public`）は、取れなかった範囲を報告に書く。MCP未接続や権限不足の操作は、その操作だけを飛ばして理由を記録し、残りを続ける。`permalink` の取れない発言は、元へ戻れないので写さない。どう取るかの詳細は[対象別の収集方法](references/targets.md)にある。

## 手順

1. **設定を読み、計画を組む。** `python3 scripts/config.py read --repo <repository配下のpath>` で `<git root>/.harness-plugins/collect-slack.config.yml` を読む。設定が無いか形が違えば、終了code `2` と診断が返るので止まる。記入例は [`assets/collect-slack.config.example.yml`](assets/collect-slack.config.example.yml) にある。続けて `python3 scripts/message.py plan --config <readが返したconfig>` で計画を得る。
2. **対象日を決める。** 指定が無ければ設定の `timezone` の当日にし、報告に書く。範囲の ts は `scripts/date-range.py --date <YYYY-MM-DD> --timezone <timezone>` で得る。
3. **計画を順に実行する。** バケットごとに、取る前に `message.py check` の `decision` を見る。`new` と `updated` は取得して書き、`unchanged` は何もせず、`recheck` は対象日の全範囲を取り直して編集を突き合わせる。
4. **書く。** 取得した発言を1行1 JSONの一時fileにし、[保存工程](references/workflow.md)の `message.py append` へ渡す。重複排除、整列、front matter、台帳の更新はscriptが行う。`check` か `append` が `2` を返したバケットは、保存済みとして扱わない。
5. **報告する。** 対象日、見たワークスペース、バケットごとの新規と総数、`credential_redacted` の合計、飛ばした対象とその理由、保存先を報告する。0件でも0件と書く。

取得結果に無いことを削除と推定しない。明示的な削除通知だけを `deleted=true` にし、APIが返さない編集や削除は反映できないことを報告に書く。
