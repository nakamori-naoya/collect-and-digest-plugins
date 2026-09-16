---
name: make-session-digest
description: collect-sessionsの非公開索引を使い、対象日に活動したClaude Code / CodexセッションごとのIDと短い要約を1本の日次記録へ保存する。「今日のエージェント作業をまとめて」「セッションを日報にして」「session digest」と依頼されたときに使う。
---

# make-session-digest

セッション原文を複製せず、対象日に活動したセッションごとの不透明IDと短い要約を1本のMarkdownへ保存する。読み終えた利用者は、その日にどのセッションで何をしたかを後から仕事へ再利用できる粒度で振り返れる。

## 入力

- `user_input`: 対象日の指定を含む依頼。指定が無ければ `output.timezone` の当日。
- `references`: 任意。追加で従う資料の絶対path配列。手順の最初に読み、`write-doc` の `references` へ加える。プロジェクト固有の規約や文脈は、対象repositoryのAGENTS.md / CLAUDE.mdとこの入力で渡される。
- 同じdirectoryの [`playbook.yml`](playbook.yml) の `output`（`dir` / `format` / `timezone` / `subagents`）と `contract`（`session_item_fields` / `document_type` / `output_name`）。同じagentがこのYAMLを読み、`steps` の宣言順を実行順の正本にする。
- 収集済みの日次索引: 同じpackageの公開skill `collect-sessions` が `state_dir` に作る。その設定は利用者の `collect-sessions.config.yml` にあり、この入口は読まない。

## 判断基準

- **索引は確定しているか。** `collect-sessions` が `partial` または `provisional` を返したら止まり、日次資料を作らない。
- **何を残し、何を混ぜないか。** material の `source_path` は要約時だけ読み、全文や中間要約を保存しない。material自体もfileに書かない。残すもの・混ぜないものは[privacy境界](references/privacy.md)に従う。本文の見出し、front matterの形、タグの形は `write-doc` の `agent-session-digest` 型のtemplateが定め、この入口は素材を `kind: text` で渡して `document_type: agent-session-digest` で保存するだけである。front matterの各値の意味と保存の判断は[日次記録の契約](references/output.md)に従う。各セッションから後で仕事へ再利用できる事実と判断を選び、必要な根拠を文字数で機械的に削らない。
- **既存資料があるか。** 成果物は `<output.dir>/<対象日>.md`。同名の既存資料があるときは依頼する前に既存を読み、front matterの `input_hash` を比較する。同じなら何も依頼せず終える。異なり、かつ利用者がその既存pathの更新を明示しているときだけ `update_target` を渡す。明示が無ければ資料化を依頼しない。0件では空の成果物を書かない。
- **subagentを含めるか。** `output.subagents` が `include` のときだけsubagent分を含める。

## 手順

1. **収集する（`collect`）。** 同じpackageの公開skill `collect-sessions` の手順で対象日の索引を確定し、返った `index` / `target_date` / `provisional` を使う。外部runtimeが `target_date` を注入したことにせず、collectが返した値だけを後続へ渡す。
2. **materialをまとめる（`material`）。** `python3 scripts/material.py --day-index <index> --date <target_date> [--include-subagents]` を実行する。入力は索引の絶対pathと対象日、出力は標準出力のJSON 1 objectで、`artifact.material`（セッションごとのrecordsの配列。keyは `contract.session_item_fields`）、`artifact.input_hash`、`artifact.target_date`、`artifact.session_count`、`counts.items` を持つ。fileは書かない。終了codeは `0` = 組み立てた、`2` = 索引不在・読めない・provisional / 未完成のセッション・原文の欠落、`4` = 対象日に完成済みのroot sessionが無い（診断は標準出力のJSON `error`）。`0` 以外なら止まる（`4` は0件として報告する）。
3. **資料化を委譲する（`document`）。** 公開Skill `write-doc:write-doc` へ次を直接渡す。`material` は手順2の `artifact.material` をJSON文字列にして `{kind: text, content: <JSON文字列>}` にした1要素の配列（fileに書いてから渡さない。`items` のような別名やセッション配列そのものは渡さない）。`document_type` は `contract.document_type`（`agent-session-digest`）。`output_directory` は `output.dir` を展開した絶対path、`name` は `contract.output_name` の `<target_date>` を対象日へ置換した `.md` 名。更新の明示があるときだけこの2つに代えて `update_target`。`references` は入力の `references` をそのまま渡す。返ったobjectの `status` が `completed` なら `path` を最終資料、`failed` なら `reason` を報告して止まる。

## 停止条件

止まるのは次の場合である。診断または `reason` を報告し、資料が書けたことにしない。

- `collect-sessions` が `partial` / `provisional` を返した。索引が確定していないので日次資料を作らない。
- `material.py` が `2` を返した（索引不在・読めない・provisional / 未完成のセッション・原文の欠落）。
- 同名の既存資料があり `input_hash` が異なるのに、利用者がその更新を明示していない。既存fileの上書きは許可が要るので、差分があることを報告して止まる。
- `write-doc` が `failed` を返した。

次は止まらず、記録して進む。

- 対象日の指定が無い。`output.timezone` の当日を対象日として進め、報告に明記する。
- 同名の既存資料があり `input_hash` が同じ。何も依頼せず「変更なし」と報告して終える。
- セッションが0件（`material.py` が `4`）。空の成果物を書かず、0件と報告する。

## 出力

`<output.dir>/<対象日>.md` の絶対pathと、セッション数、`input_hash` の報告。
