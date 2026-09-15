---
name: make-session-digest
description: session-collectの非公開索引を使い、対象日に活動したClaude Code / CodexセッションごとのIDと短い要約を1本の日次記録へ保存する。「今日のエージェント作業をまとめて」「セッションを日報にして」「session digest」と依頼されたときに使う。
---

# make-session-digest（日次セッション記録）

セッション原文を複製せず、対象日に活動したセッションごとの不透明IDと短い要約を1本のMarkdownへ保存する。

## 1. 実行契約を受け取る

このSKILLを実行する同じagentが、同じdirectoryの`playbook.yml`と本文から参照する資料を全文読み、利用者の入力と明示された資料を保持した一つの文脈で最後まで判断する。本文の`${.playbook...}`と`${.instructions...}`は、agentが`playbook.yml`から読んだ値を指し、外部runtimeから注入される値ではない。認知工程を別skillへrelayせず、`skill:`工程の責務と参照資料をこのagent自身が適用する。決定論的な`script:`工程は同じdirectoryの実在するtoolへ明示した入力pathを渡し、stdoutまたは指定した出力pathから結果を受け取る。`playbook:`工程だけは依存先の公開Skillを名前で呼び、その公開入力と公開結果だけを使う。設定生成、scope、依存先rootの探索、一時設定の寿命管理は行わない。必要な入力、宣言値、tool結果、公開Skill結果が無ければ推測せず停止する。

`${.instructions.execution.directive}` / `${.playbook.output.dir}` / `${.playbook.output.timezone}` / `${.playbook.output.subagents}` / `${.playbook.contract}` / `${.playbook.steps}`に従う。資料化と保存は依存先`write-doc`の公開playbookへ委譲する（手順は3節）。相手の中の作りを前提にせず、契約の入力・出力だけでやり取りする。

## 2. 工程を実行する

`${.playbook.steps}`の責務を同じagentが上から実行し、needsが揃わない工程は開始しない。collectがpartialまたはprovisionalを返したら停止し、日次資料を作らない。

`collect`は公開入力`user_input`を受け、同じagentが適用する`collect-sessions`の実在手順で対象日を確定する。外部runtimeが`target_date`を注入したことにせず、collectが直接返した`target_date`だけを後続工程へ渡す。

material工程ではsession-collectが返したday indexを次へ渡す。同じagentがrepository外にrun専用subdirectoryを作り、HOME、TMPDIR root、共有directoryそのものを使わない。`${.playbook.output.subagents}`が`include`のときだけsubagent分を含める。

## 3. write-docへ資料化を委譲する

material内の`source_path`は要約時だけ読む。全文や中間要約を保存しない。何を残し、何を混入させないかは[privacy境界](references/privacy.md)、本文・metadata・タグの形は[日次記録の契約](references/output.md)に従う。各セッションから後で仕事へ再利用できる事実と判断を選び、必要な根拠を文字数で機械的に削らない。

`document`工程で公開Skill `write-doc:write-doc`へ、次の入力objectを直接渡す。中間ファイルや依存先の実行状態は作らない。

- `material`: material工程が返した`material_path`を`{kind: file, path: <絶対path>}`にした1要素のobject配列
- `document_type`: `${.playbook.contract.document_type}`の値
- `output_directory`: `${.playbook.output.dir}`を展開した絶対path
- `name`: `${.playbook.contract.output_name}`の`<target_date>`を対象日へ置換した`.md`ファイル名
- `references`: `references/output.md`と`references/privacy.md`の読み取り可能な絶対path配列

`items`という別名や、material内のセッション配列そのものを`material`へ渡さない。公開YAMLのdocument工程は`material_path`をneedし、この1つの絶対pathから上記のtyped `material`を同じagentが組み立てる。`material_path`が無い、通常ファイルでない、または読み取れない場合はwrite-docを呼ばず停止する。

新規作成では`output_directory`と`name`を必ず組にする。既存資料を同じpathへ更新すると利用者が明示した場合だけ、この2つに代えて`update_target`へ確認済みの絶対pathを渡す。両方式を同時に渡さない。

公開playbookが直接返した`status`を確認する。`completed`なら`path`をdocument工程の`path`として次へ渡す。`failed`なら`reason`を報告して停止し、資料が書けたことにしない。返却値に`path`と`reason`の両方がある場合や、契約にない値がある場合も停止する。

### 同じpathに既存資料があるとき

成果物は`<output.dir>/<対象日>.md`。同名の既存資料があるときは、**依頼する前に**こちらで既存を読み、front matterの`input_hash`を比較する。同じなら何も依頼せず終了する。異なり、かつ利用者からその既存pathの更新が明示されているときだけ、3-1で`update_target`にその絶対pathを書く。明示が無ければ資料化を依頼しない。独自の保存scriptやforceオプションは持たない。0件では空の成果物を書かない。

cleanupはdocumentが返した`path`とcollectが返した`index`、今回の`material_path`が揃った後にだけ同じagentが実行する。決定論的toolから直接受け取った出力object全体を`cleanup_report`として扱う。cleanupが削除してよいのは今回のmaterial file 1件だけであり、0700のrun専用directoryは残す。
