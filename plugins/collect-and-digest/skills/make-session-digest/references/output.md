# 日次記録の契約

本文の見出しとfront matterの形は、`write-doc` の `agent-session-digest` 型のtemplateが定める。この入口が持つのは、front matterの各値をどう決めるか、タグに何を入れてよいか、いつ保存を依頼するかの判断である。

## front matterの各値

最終Markdownのfront matterに`schema: 2`、`kind: agent-session-digest`、`target_date`、`timezone`、`input_hash`、`generated_at`、`session_count`、`summary_schema`、`sessions`、`generator`、`validation`、`human_reviewed`、`tags`を持たせる。本文とは別のmetadataファイルを作らない。

- `sessions`: `source`、不透明化済み`source_id`、索引の`observed_at`。どのセッションをいつ収集したかを残す。
- `generator`: 実際に要約した`model`と、文書型の名前を指す`prompt_ref`。不明な値を推測しない。
- `validation`: `privacy`、`structure`、`source_unchanged`を`passed` / `failed` / `not_checked`で記録する。実行していない検証は`not_checked`にする。
- `human_reviewed`: 保存時は原則`false`。人が内容を確認したときだけ別の明示的な操作で`true`にする。
- `tags`: `projects`、`repositories`、`purposes`、`decisions`、`open_questions`の配列を持つ。

タグは将来の日次横断集約に使う。原文から顧客名、repository名、案件名を推測して入れない。利用者が設定または依頼で明示した公開可能なaliasだけを使い、それ以外は空配列にする。文章ではなく短く安定した値にし、同じ対象へ表記揺れを作らない。

`write-doc`へ渡す前に各値をこの契約に照らして検査し、失敗状態を含む資料は保存しない。materialはfileに書かず、`material.py`の標準出力からそのまま`kind: text`の素材として渡す。保存後に消すべき一時fileは無い。生成要約も原文と同じ機密度として扱う。

## 保存契約

最終Markdownの保存は`write-doc`だけが行う。素材、文書型、保存先、追加参照を公開契約の入力objectとして直接渡す。

新規に作るか、既存の資料を更新するかは、session-digest側が先に決める。同名の既存資料があるかを見て、front matterの`input_hash`が同じなら、何も依頼しない。新規に作るときは、`<target_date>.md`を`name`として渡し、保存先directoryはこのplaybookの設定が決めているので`output_directory`もあわせて渡す（任意のキーだが、渡すなら`name`が要る）。既存の資料を同じpathへ更新すると決めたときは、`output_directory`と`name`を渡さず、確認済みの絶対pathを`update_target`として渡す。`name`と`update_target`は同時に渡せない。

session-digest固有の保存・置換scriptは持たない。保存結果は公開playbookが直接返した`status`と`path`または`reason`として受け取る。
