---
name: make-session-digest
description: collect-sessionsの非公開索引を使い、対象日に活動したClaude Code / CodexセッションごとのIDと短い要約を1本の日次記録へ保存する。「今日のエージェント作業をまとめて」「セッションを日報にして」「session digest」と依頼されたときに使う。
---

# make-session-digest

セッションの原文を複製せず、対象日に活動したセッションごとの不透明IDと短い要約を、1本のMarkdownとして保存する。利用者は、その日にどのセッションで何をしたかを、後の仕事に使い回せる粒度で振り返れる。本文の見出しとfront matterの形は `write-doc` の `agent-session-digest` 型が持ち、この入口は素材と保存先を渡すだけである。工程の順は同じdirectoryの [`playbook.yml`](playbook.yml) にある。

## 入力

依頼の `user_input` から対象日を読む。指定が無ければ `collect-sessions` の設定の timezone での当日にする。保存先directoryの絶対pathを `output_directory` で受け取る。無ければ、どこへ保存するかで成果物の置き場が変わるので、止まって利用者に問う。subagent の分は、利用者が含めると言ったときだけ含める。任意の `references` は、最初に読んで `write-doc` へそのまま渡す。

## 要約は共有されるものとして書く

原文にあったことは、日次記録へ書いてよい理由にならない。人や顧客ではなく役割と判断を、secret ではなく「認証設定を更新した」のような作業の意味を、pathやrepository名ではなく変更の種類を書く。迷う情報はぼかして残さず省き、省くと要る意味まで失うなら、要約をやめて止まる。伏せ字、先頭の数文字、hash化は匿名化ではない。出さないものの一覧は `agent-session-digest` 型に従う。原文は要約するときにだけ読み、全文も途中の要約もfileに書かない。

タグには、利用者が設定か依頼で明示した公開可能な別名だけを入れる。原文から顧客名、repository名、案件名を推測して入れない。明示が無ければ空にする。

## 手順

1. **索引を確定する。** 同じpackageの `collect-sessions` の手順で対象日の索引を作り、返った `index`、`target_date`、`provisional` を使う。`partial` か `provisional` なら、索引が確定していないので止まる。
2. **素材をまとめる。** `python3 scripts/material.py --day-index <index> --date <target_date> [--include-subagents]` を実行する。標準出力のJSONの `artifact.material` がセッションごとのrecords、`artifact.input_hash` が素材のhashである。終了code `2` は索引や原文の欠落なので止まり、`4` は0件なので空の資料を書かずに0件と報告する。
3. **既存の記録と比べる。** `<output_directory>/<target_date>.md` が既にあれば、そのfront matterの `input_hash` と比べる。同じなら何もせず「変更なし」と報告する。違うときは、利用者がその既存fileの更新を明示している場合だけ進む。明示が無ければ、既存fileの上書きには許可が要るので、差分があることを報告して止まる。
4. **資料化を任せる。** 公開Skill `write-doc:write-doc` へ、`artifact.material` をJSON文字列にした `{kind: text, content: <JSON文字列>}` 一つだけの `material`、`document_type: agent-session-digest`、`output_directory` と `name: <target_date>.md`（更新なら、この二つに代えて既存fileの `update_target`）、入力の `references` を渡す。`status` が `completed` なら `path` を報告し、`failed` なら `reason` を報告して止まる。

## 出力

保存した日次記録の絶対path、セッション数、`input_hash` を報告する。
