# 2026-W38（2026-09-14〜2026-09-20）決済チーム ダイジェスト

この週、返金APIのリリース日は 9/24 から 10/1 へ延び、部分返金の手数料は加盟店が負担すると決まった。延期の理由になった負荷試験の p99 は 620ms まで下がったが、目標の 500ms にはまだ届いておらず、改善の担当も決まっていない。返金ログを何年残すかという問いも新しく開いた。

このダイジェストは、次回の決済チーム定例に出る人が、10/1 のリリースに向けて「未決のまま」の二つの論点から話し始めるためのもの。定例の議事の順序や負荷試験の詳しい分析は扱わない。素材は定例2回と #payments のスレッド1件である。

## 決まったこと

| 決定 | いつ | 誰が | 出典 |
|---|---|---|---|
| 部分返金の決済手数料は加盟店が負担する | 2026-09-17 | 佐藤（経理の山本さんの回答を受けて） | [決済チーム定例 2026-09-17](https://www.notion.so/example/0917-teirei) |
| 返金APIのリリースを 9/24 から 10/1 に延ばす | 2026-09-17 | 佐藤 | [決済チーム定例 2026-09-17](https://www.notion.so/example/0917-teirei) |

9/14 の定例では、佐藤がリリース日を 9/24 と決めていた（[決済チーム定例 2026-09-14](https://www.notion.so/example/0914-teirei)）。その後、負荷試験の p99 が目標に届かなかったため、9/17 に 10/1 へ改めた。いま有効なのは 10/1 である。

部分返金の手数料は、9/14 の時点ではどちらが負担するか決まっておらず、経理に確認することになっていた。9/17 に経理から加盟店負担と回答があり、田中が読んだ決済代行会社の規約12条にも同じことが書かれていたので、この論点は閉じた。

## 未決のまま

- **p99 を下げる作業を誰が担当するか。** 9/17 の定例では「誰かが見ておく」で終わり、担当を決めていない。担当と期限が決まれば閉じる。10/1 のリリースはこの改善を前提にしているので、次回の定例で最初に決めたい論点である。2026-09-17 から開いている（[決済チーム定例 2026-09-17](https://www.notion.so/example/0917-teirei)）。
- **監査の対応で、返金のログを7年残す必要があるか。** 今の保持期間の設定は1年である。田中の問いに佐藤が「法務に聞いてみないと分からない」と答えた段階で、法務へ誰が聞くかも決まっていない。法務の回答が出れば閉じる。2026-09-18 から開いている（[#payments 田中の投稿](https://example-team.slack.com/archives/C0PAY/p1789715400000200)、[佐藤の返信](https://example-team.slack.com/archives/C0PAY/p1789716000000300)）。

## アクション

- 決済代行会社の手数料の規約を読み、部分返金の扱いを報告する。田中、期限は 2026-09-17 で、完了した（[決済チーム定例 2026-09-14](https://www.notion.so/example/0914-teirei)、[決済チーム定例 2026-09-17](https://www.notion.so/example/0917-teirei)）。

担当の決まった作業は、この週にはこの1件だけである。p99 の改善と法務への確認は担当が決まっていないため、アクションではなく「未決のまま」に載せている。

## この期間の動き：p99 は 620ms まで下がったが、目標の 500ms には届いていない

返金APIの p99 は、ステージングで 1000rps の負荷をかけた試験で、9/14 の時点では 800ms だった（[決済チーム定例 2026-09-14](https://www.notion.so/example/0914-teirei)）。9/18 に鈴木が接続プールを広げて同じ 1000rps で30分試したところ、620ms まで下がった（[#payments 鈴木の投稿](https://example-team.slack.com/archives/C0PAY/p1789714800000100)）。それでも目標の 500ms まではあと 120ms ある。

9/17 の定例で鈴木は「たぶん来週には直せると思う」と話したが、これは見込みであり、担当や期限として決まったものではない。10/1 のリリースに間に合うかは、まだ確かめられていない。

## 素材

| 日付 | ソース | タイトル |
|---|---|---|
| 2026-09-14 | notion | [決済チーム定例 2026-09-14](https://www.notion.so/example/0914-teirei) |
| 2026-09-17 | notion | [決済チーム定例 2026-09-17](https://www.notion.so/example/0917-teirei) |
| 2026-09-18 | slack | [#payments](https://example-team.slack.com/archives/C0PAY/p1789714800000100) |

拾わなかった素材は1件である。`notes/2026-09-16/メモ.md` は front matter が無く、日付と出典を確かめられないため使っていない。

## 資料の情報

| 項目 | 値 |
|---|---|
| digest | weekly |
| 型 | period-digest |
| 期間 | 2026-09-14〜2026-09-20（2026-W38） |
| 作成 | 2026-09-27T11:06:20+09:00 |
| 参加者 | 佐藤、田中、鈴木、山本（経理） |
| ラベル | digest:weekly、type:period-digest、period:2026-W38、source:notes、source:slack |

参加者は定例の議事録の参加者欄から取った。Slack の投稿者 sato、tanaka、suzuki は、それぞれ佐藤、田中、鈴木と同じ人と推定しているが、未確認である。

<!-- doc-meta:begin
{"schema": 1, "producer": "weekly", "digest": "weekly", "type": "period-digest", "period": {"from": "2026-09-14", "to": "2026-09-20", "label": "2026-W38"}, "generated_at": "2026-09-27T11:06:20+09:00", "participants": ["佐藤", "田中", "鈴木", "山本（経理）"], "participants_note": "定例の議事録の参加者欄から取った。Slackの投稿者 sato / tanaka / suzuki は佐藤・田中・鈴木と同一人物と推定（未確認）。", "labels": ["digest:weekly", "type:period-digest", "period:2026-W38", "source:notes", "source:slack"], "materials": [{"path": "/private/tmp/e-FCVpCX/home/cwd/notes/2026-09-14/決済チーム定例.md", "dir": "/private/tmp/e-FCVpCX/home/cwd/notes", "date": "2026-09-14", "source": "notion", "source_id": "notion-page-0914", "url": "https://www.notion.so/example/0914-teirei", "title": "決済チーム定例 2026-09-14", "occurred_at": "2026-09-14T10:00:00+09:00", "parts": false, "bytes": 840}, {"path": "/private/tmp/e-FCVpCX/home/cwd/notes/2026-09-17/決済チーム定例.md", "dir": "/private/tmp/e-FCVpCX/home/cwd/notes", "date": "2026-09-17", "source": "notion", "source_id": "notion-page-0917", "url": "https://www.notion.so/example/0917-teirei", "title": "決済チーム定例 2026-09-17", "occurred_at": "2026-09-17T10:00:00+09:00", "parts": false, "bytes": 973}, {"path": "/private/tmp/e-FCVpCX/home/cwd/slack/2026-09-18/thread-C0PAY-1789714800000100.md", "dir": "/private/tmp/e-FCVpCX/home/cwd/slack", "date": "2026-09-18", "source": "slack", "source_id": "thread-C0PAY-1789714800000100@2026-09-18", "url": "https://example-team.slack.com/archives/C0PAY/p1789714800000100", "title": "#payments", "occurred_at": "", "parts": false, "bytes": 1310}]}
doc-meta:end -->
