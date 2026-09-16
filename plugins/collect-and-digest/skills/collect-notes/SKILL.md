---
name: collect-notes
description: Notion / Google Docsの議事録のうち、設定timezone上の対象日（既定は今日）に属するものを1箇所へ集めて保存する。要約も抽出もしない。「議事録を集めて」「collect-notes」「今日のミーティングノートを取り込んで」と言われたときに使う。
---

# collect-notes

対象日に属する議事録を、原文のまま `<notes_dir>/<対象日>/` へ落とす。正本は常に上流（Notion / Google Docs）であり、ここに置くのはその写しで、書き戻す動線は作らない。抽出、要約、伏せ字、truncationはしない。資料化やチケット化は別の仕事である。

## 入力

- 対象日: 利用者が `--date 2026-08-12` のように指定した日。指定が無ければ設定の `timezone` での当日。directoryのキーは対象日であって起動日ではない（0:30に前日分を回収しても前日のdirectoryへ入る）。
- 設定file: `<repository root>/.harness-plugins/collect-notes.config.yml`。1層で必須、同梱既定へのfallbackは無い。keyは `version: 1`、`notes_dir`（相対ならrepository root基準。git管理下は拒否される）、`timezone`、`collect.sources.notion.enabled`、`collect.sources.google_docs.enabled`（任意で `drive_query`）、`collect.transcript`、`collect.max_bytes`。記入例は [`assets/collect-notes.config.example.yml`](assets/collect-notes.config.example.yml)。fileが無い、keyが足りない・余る、型や値が許容範囲外なら `note.py` が診断を返して止まる。

## 判断基準

- **有効なsourceか。** `collect.sources.<name>.enabled` が `true` のsourceだけを処理する。Notionは[Notionの収集方法](references/sources/notion.md)、Google Docsは[Google Docsの収集方法](references/sources/google-docs.md)に従う。MCPが使えないsourceは理由を記録してスキップし、収集全体を止めない。
- **取る前に判定したか。** 1件ごとに `note.py check` の `decision` を見る。`new` は取得して書く、`updated` は取得して書き直す、`unchanged` は何もしない、`recheck` は本文を取得してhashで判定する。
- **原文のままか。** 本文、日時、参加者、録画URL、DBプロパティを取れる範囲で保存し、推定しない。上限超過は部分保存せず止まる。
- **0件でも報告するか。** 0件は「0件だった」と報告し、黙って終わらない。

## 手順

1. **設定と保存先を確かめる。** `python3 scripts/note.py paths --config <設定file> --target-date <YYYY-MM-DD>` を実行する。入力は設定fileの絶対pathと対象日、出力は `notes_dir` と `date_dir` を持つ標準出力のJSON、終了codeは `0` = 設定を読めた、`2` = 設定file不在または schema 違反（診断は標準出力のJSON `error`）。`2` なら止まる。
2. **対象日を決める。** 指定が無ければ `timezone` の当日を使う。対象日の判定は[収集工程の詳細](references/workflow.md)に従う。
3. **1件ずつ判定する。** `python3 scripts/note.py check --config <設定file> --source notion --source-id <ID> --source-updated-at <上流の更新時刻>` を実行する。出力は `decision` を持つ標準出力のJSON、終了codeは `0` = 判定した、`2` = 引数・設定の不備。
4. **書く。** [収集工程の詳細](references/workflow.md)の `note.py write` へ原文Markdownの一時fileと取得したmetadataを渡す。scriptがfront matter、台帳、副文書（文字起こし）を書く。終了codeは `0` = 保存した、`2` = 不備または上限超過（診断は標準出力のJSON `error`）。`2` ならその1件を保存済みとして扱わない。
5. **報告する。** 対象日、新規・更新・変更なしの件数とタイトル、スキップ理由、保存先を報告する。

会議保存は本文と全metadataのhashで更新を判断し、`source_updated_at` だけの更新も台帳とfront matterへ反映する。対象日が変わった場合は旧日の主文書・transcriptを履歴として保持し、最新台帳のpathを現行文書として扱う。transcriptが後から省略された場合も旧副文書を履歴として保持し、現行主文書の `parts` に無い副文書を現行データと見なさない。保存directory単位の排他とredo journalで本文・副文書・台帳の中断回復を行う。

## 停止条件

- 設定fileが無い、または schema に合わない。`note.py` の診断を報告して止まる。
- `note.py write` が `2` を返した（上限超過を含む）。その1件を保存済みとして扱わず、診断を報告する。

## 出力

保存先 `<notes_dir>/<対象日>/` の写しと台帳の更新。報告は手順5の項目を持つ。
