# 日次記録の契約

## 本文

セッションごとに不透明化したIDとsource表示名を置き、次の見出しをこの順で持つ。該当しない節も省略せず`なし`と書く。

1. 達成したこと
2. 変更した対象
3. 採用した判断と理由
4. 却下した選択肢
5. 実行した検証と結果
6. 未解決事項
7. 次にやること

会話の時系列や発言の言い換えではなく、後から仕事へ再利用できる事実と判断を書く。1セッションの本文全体を設定された文字数内に収める。

## front matter

最終Markdownのfront matterに`schema: 2`、`kind: agent-session-digest`、`target_date`、`timezone`、`input_hash`、`generated_at`、`session_count`、`summary_schema`、`sessions`、`generator`、`validation`、`human_reviewed`、`tags`を持たせる。本文とは別のmetadataファイルを作らない。

- `sessions`: `source`、不透明化済み`source_id`、索引の`observed_at`。どのセッションをいつ収集したかを残す。
- `generator`: 実際に要約した`model`と、この契約を指す`prompt_ref`。不明な値を推測しない。
- `validation`: `privacy`、`structure`、`source_unchanged`を`passed` / `failed` / `not_checked`で記録する。実行していない検証は`not_checked`にする。
- `human_reviewed`: 保存時は原則`false`。人が内容を確認したときだけ別の明示的な操作で`true`にする。
- `tags`: `projects`、`repositories`、`purposes`、`decisions`、`open_questions`の配列を持つ。

タグは将来の日次横断集約に使う。原文から顧客名、repository名、案件名を推測して入れない。利用者が設定または依頼で明示した公開可能なaliasだけを使い、それ以外は空配列にする。文章ではなく短く安定した値にし、同じ対象へ表記揺れを作らない。

`write-doc`へ渡す前に各値をこの契約に照らして検査し、失敗状態を含む資料は保存しない。materialファイルは0600で作る。資料化後は今回の`material_path`、最終Markdownの`path`、入力day indexの`index`を`material.py --cleanup`へ渡す。出力JSON全体を`cleanup_report`として扱い、cleanupはmaterial file 1件だけをunlinkして0700の実行専用directoryは残す。生成要約も原文と同じ機密度として扱う。

## 保存契約

最終Markdownの保存は`write-doc`だけが行う。新規作成では`<target_date>.md`をnameとして渡し、既存資料の更新では確認済みの絶対pathを`update_target`として渡す。session-digest固有の保存・置換scriptは持たない。
