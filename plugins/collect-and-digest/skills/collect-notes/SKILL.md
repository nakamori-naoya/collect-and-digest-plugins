---
name: collect-notes
description: Notion / Google Docsの議事録のうち、設定timezone上の対象日（既定は今日）に属するものを1箇所へ集めて保存する。要約も抽出もしない。「議事録を集めて」「collect-notes」「今日のミーティングノートを取り込んで」と言われたときに使う。
---

# collect-notes

対象日に属する議事録を、原文のまま `<notes_dir>/<対象日>/` へ写す。元の記録は常にNotionやGoogle Docsにあり、ここに置くのはその写しである。資料化やチケット化は別の仕事である。

## 上流は読むだけにし、写すだけにする

NotionとGoogle Docsは読むだけで、ページの作成、更新、コメントのような書き込みの tool は使わない。写しを作る仕事で、利用者の許可なく他人の目に触れる場所を変えないためである。本文、日時、参加者、録画URL、DBプロパティは取れた範囲をそのまま保存し、取れないものを推定で補わず、省いた項目として記録する。要約、伏せ字、切り詰めはしない。上限を超えた1件は部分保存せず、保存済みとして扱わない。

設定で有効にした source だけを読む。MCPが使えない source は理由を記録して飛ばし、残りを続ける。source ごとの取り方は、Notionは[Notionの収集方法](references/sources/notion.md)、Google Docsは[Google Docsの収集方法](references/sources/google-docs.md)にある。

## 手順

1. **設定を読み、保存先を確かめる。** `python3 scripts/config.py read --repo <repository配下のpath>` で `<git root>/.harness-plugins/collect-notes.config.yml` を読む。設定が無いか形が違えば、終了code `2` と診断が返るので止まる。記入例は [`assets/collect-notes.config.example.yml`](assets/collect-notes.config.example.yml) にある。続けて `python3 scripts/note.py paths --config <readが返したconfig> --target-date <YYYY-MM-DD>` で保存先を得る。
2. **対象日を決める。** 指定が無ければ設定の `timezone` の当日にする。各議事録の日付は `occurred_at` を設定の timezone に直して決め、取れなければ上流の作成日時で代え、その根拠を報告に書く。
3. **1件ずつ、取る前に判定する。** `python3 scripts/note.py check` の `decision` を見る。`new` は取得して書き、`updated` は書き直し、`unchanged` は何もせず、`recheck` は本文を取得してhashで判定する。
4. **書く。** [収集工程の詳細](references/workflow.md)の `note.py write` へ、原文Markdownの一時fileと取得したmetadataを渡す。front matter、台帳、文字起こしの副文書はscriptが書く。`2` が返った1件は保存済みとして扱わない。
5. **報告する。** 対象日、新規・更新・変更なしの件数とタイトル、飛ばした source とその理由、保存先を報告する。0件でも0件と書く。
