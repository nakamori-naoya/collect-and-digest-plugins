---
name: make-session-digest
description: collect-sessionsの非公開索引を使い、対象日に活動したClaude Code / CodexセッションごとのIDと短い要約を1本の日次記録へ保存する。「今日のエージェント作業をまとめて」「セッションを日報にして」「session digest」と依頼されたときに使う。
---

# make-session-digest

セッション原文を複製せず、対象日に活動したセッションごとの不透明IDと短い要約を1本のMarkdownへ保存する。読み終えた利用者は、その日にどのセッションで何をしたかを後から仕事へ再利用できる粒度で振り返れる。

## 入力

- `user_input`: 対象日の指定を含む依頼。指定が無ければ `output.timezone` の当日。
- 同じdirectoryの [`playbook.yml`](playbook.yml) の `output`（`dir` / `format` / `timezone` / `subagents`）と `contract`（`session_item_fields` / `document_type` / `output_name`）。同じagentがこのYAMLを読み、`steps` の宣言順を実行順の正本にする。
- 収集済みの日次索引: 同じpackageの公開skill `collect-sessions` が `state_dir` に作る。その設定は利用者の `collect-sessions.config.yml` にあり、この入口は読まない。

## 判断基準

- **索引は確定しているか。** `collect-sessions` が `partial` または `provisional` を返したら止まり、日次資料を作らない。
- **何を残し、何を混ぜないか。** material内の `source_path` は要約時だけ読み、全文や中間要約を保存しない。残すもの・混ぜないものは[privacy境界](references/privacy.md)、本文・metadata・タグの形は[日次記録の契約](references/output.md)に従う。各セッションから後で仕事へ再利用できる事実と判断を選び、必要な根拠を文字数で機械的に削らない。
- **既存資料があるか。** 成果物は `<output.dir>/<対象日>.md`。同名の既存資料があるときは依頼する前に既存を読み、front matterの `input_hash` を比較する。同じなら何も依頼せず終える。異なり、かつ利用者がその既存pathの更新を明示しているときだけ `update_target` を渡す。明示が無ければ資料化を依頼しない。0件では空の成果物を書かない。
- **subagentを含めるか。** `output.subagents` が `include` のときだけsubagent分を含める。

## 手順

1. **収集する（`collect`）。** 同じpackageの公開skill `collect-sessions` の手順で対象日の索引を確定し、返った `index` / `target_date` / `provisional` を使う。外部runtimeが `target_date` を注入したことにせず、collectが返した値だけを後続へ渡す。
2. **materialをまとめる（`material`）。** repository外にrun専用の0700 subdirectoryを作り（HOME、TMPDIR root、共有directoryそのものは使わない）、`python3 scripts/material.py --day-index <index> --date <target_date> --out-dir <run専用directory> [--include-subagents]` を実行する。出力は `material_path` / `input_hash` / `target_date` / `session_count` を持つ標準出力のJSON、終了codeは `0` = 作った、`2` = 索引不在・読めない・out-dirの安全違反（診断は標準出力のJSON `error`）。`2` なら止まる。
3. **資料化を委譲する（`document`）。** 公開Skill `write-doc:write-doc` へ次を直接渡す。`material` は `material_path` を `{kind: file, path: <絶対path>}` にした1要素の配列（`items` のような別名やセッション配列そのものは渡さない）。`document_type` は `contract.document_type`（`period-digest`）。`output_directory` は `output.dir` を展開した絶対path、`name` は `contract.output_name` の `<target_date>` を対象日へ置換した `.md` 名。更新の明示があるときだけこの2つに代えて `update_target`。`references` は `references/output.md` と `references/privacy.md` の絶対path。返ったobjectの `status` が `completed` なら `path` を後続へ渡し、`failed` なら `reason` を報告して止まる。
4. **後片付けする（`cleanup`）。** `document` が返した `path`、collectが返した `index`、今回の `material_path` が揃った後だけ `python3 scripts/material.py --cleanup --material-path <material_path> --path <path> --index <index>` を実行する。削除してよいのは今回のmaterial file 1件だけで、run専用directoryは残す。終了codeは `0` = 削除した、`2` = 引数不備または保護対象（診断は標準出力のJSON `error`）。出力object全体を `cleanup_report` として報告する。

## 停止条件

- `collect-sessions` が `partial` / `provisional` を返した。日次資料を作らず理由を報告する。
- `material.py` が `2` を返した。診断を報告して止まる。
- `write-doc` が `failed` を返した。`reason` を報告し、資料が書けたことにしない。

## 出力

`<output.dir>/<対象日>.md` の絶対pathと、セッション数、`input_hash`、`cleanup_report` の報告。
