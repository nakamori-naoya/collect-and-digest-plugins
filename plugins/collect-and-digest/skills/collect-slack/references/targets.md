# 何を対象にでき、どう取るか

対象は設定 `collect.targets` で個別に on/off する。`scripts/message.py plan --config <設定file>` が、設定から `collection_plan.operations` へMCP操作を決定論的に展開する。実行するのはこの計画にある操作だけで、エージェントが操作を足すことも省くこともない。

## チャンネル範囲

`collect.channels` には、次のどちらかを明示する。未指定や空配列は設定検査が拒否する。

```yaml
collect:
  channels: all              # 本人関連の検索結果をチャンネルで制限しない
```

```yaml
collect:
  channels:                  # 本人関連の検索結果とチャンネル投稿を、この範囲へ制限
    - C079CDA9H7F
    - id: C072N1VPETD
      label: "#dev"
```

`all` は、全チャンネルの全投稿を取る指定ではない。本人に関わる検索をチャンネルで制限しない、という意味である。そのため `all` では `channel_messages: false` を必須とする。

## 設定からMCP実行計画への展開

| 設定 | 追加される操作 |
|---|---|
| `direct_mentions: true` | 本人解決 → 直接メンション検索 |
| `authored_threads: true` | 本人解決 → 本人発言検索 |
| `group_mentions: true` | `groups` 1件ごとのグループメンション検索 |
| `channel_messages: true` | `channels` 1件ごとのチャンネル読み取り |
| メンション・本人発言検索のいずれか | 出力を合流・重複排除し、発見したthreadごとに読み取り |

操作の `tool`、`arguments`、`foreach` が実行契約である。実行時に置換するのは `{target_date}`、`{authenticated_user_id}`、`{thread_ref.*}` だけで、検索条件やチャンネル制限をエージェントが解釈し直すことはない。

## 使う MCP

| 用途 | ツール |
|---|---|
| チャンネルの読み取り | `slack_read_channel` |
| スレッドの読み取り | `slack_read_thread` |
| 検索（自分に関わるメンション） | `slack_search_public_and_private`（無ければ `slack_search_public`） |
| 発言者の解決 | `slack_read_user_profile` |
| リンクの取得 | 各メッセージの `permalink` |
| チャンネル名の解決 | `slack_search_channels` |

この skill は Slack を読むだけなので、`slack_send_message` のような送信系のツールは使わない。`permalink` が取れないメッセージは、元の発言へ戻れないので収集しない。

## 対象日で絞る

Slack の `ts` は epoch 秒である。対象日の設定timezoneにおける00:00と翌日00:00を境界にする。DSTがある日は、24時間とは限らない。

```bash
python3 scripts/date-range.py --date "$DATE" --timezone "<設定の timezone>"
```

検索クエリで絞るときは `on:` / `after:` / `before:` を使う。ただし検索は前後の日の発言も返すことがあるので、取得した後に各メッセージの `ts` が範囲内かを確かめ、範囲外の発言は検索のヒットにもチャンネルの投稿にも数えない。スレッドの全文だけは対象日で切らない（③）。

## `channel_messages` — 指定チャンネルの投稿

設定の `collect.channels` が配列のときだけ、列挙順に処理する。チャンネルの数に上限は無い。`all` との組み合わせは、`message.py` の設定検査が拒否する。

```yaml
collect:
  channels:
    - C079CDA9H7F                      # ID だけでよい
    - id: C072N1VPETD
      label: "#dev"                    # 表示名を付けたい場合
```

チャンネル ID が分からないときは、`slack_search_channels` で解決してから使う。推測で作った ID は、別のチャンネルを読むか、何も読めないかのどちらかになる。

1チャンネルを1バケットにし、バケット名はチャンネル ID にする。検索で見つけた親メッセージは `slack_read_thread` で返信まで辿り、返信には `thread_ts` を入れて同じバケットへ入れる。

チャンネルが多いときは、1チャンネルずつ取得から書き込みまでを終えてから次へ進む。全部を取ってからまとめて書くと、途中で失敗したときに何も残らないからである。

## `direct_mentions` / `group_mentions` / `authored_threads` — 自分が関わったスレッド

この三つは、メッセージではなくスレッドを単位に集める。スレッドのどこかに自分に関わるメンションが1件でもあれば、自分が発言していなくても、そのスレッドの全メッセージを取る。「@自分 これどう思う？」だけを保存しても何の話か分からず、前後の文脈があって初めて資料の素材になるからである。

### ① 自分に関わる発言を検索で拾う

| 何を拾うか | どう拾うか |
|---|---|
| 自分宛の直接メンション | 認証ユーザー自身への `@メンション` |
| 自分が属するグループ宛 | `collect.groups` に列挙されたグループ宛 |
| 自分の発言 | 認証ユーザー自身が投稿したメッセージ。返信先を含むスレッド全体を対象にする |

ユーザーグループの所属は API から判定できないので、自分が属するグループは設定の `collect.groups` に列挙する。`group_mentions: true` では、`collect.groups` に `id` を持つobjectを1件以上要求し、空なら `message.py` の設定検査が止める。

### ② ヒットしたメッセージから `thread_ts` を集める

メッセージに `thread_ts` があればそれを使う。無ければ、そのメッセージ自身がスレッドの親なので、`ts` を `thread_ts` として扱う。

集めた `thread_ts` は重複を除く。同じスレッドに自分宛のメンションが3回あっても、スレッドは1つである。

### ③ 各スレッドを全文取る

`slack_read_thread` で、親から末尾まで取る。対象日で絞るのは②の検索までで、スレッドの中身は対象日で切らない。スレッドは日をまたぐので、対象日で切ると会話が途中で途切れるからである。取るのは「その日に自分宛のメンションがあったスレッド」の全文である。

### ④ スレッドごとに1バケットにする

バケット名は `thread-<チャンネルID>-<thread_ts の数字部分>` にする。

```
slack/2026-08-14/thread-C123-1723526400000100.md
```

### 各メッセージに戻り先を持たせる

すべてのメッセージに `permalink` を付ける。あとから元の発言へ戻れない写しは資料の出典にならないので、`permalink` の欠けたメッセージがあると `message.py` が書き込みごと拒否する。

front matter には、チャンネルと当該リンクをタグとして静的に持たせる。こうしておくと、本文を読み直さなくても front matter だけでチャンネル別・スレッド別に束ねられる。

```yaml
tags: ["channel:C123", "channel-name:#dev", "link:https://<ws>.slack.com/archives/C123/p1723526400000100"]
thread_ts: "1723526400.000100"
thread_permalink: "https://<ws>.slack.com/archives/C123/p1723526400000100"
```

`matched` には、そのスレッドが対象になった理由（`mention_direct` / `mention_group` / `authored_by_me`）を入れる。

## 落ちるもの（`omitted` へ記録する）

| 値 | 意味 |
|---|---|
| `files` | 添付ファイルを落としていない（リンクのみ） |
| `reactions` | リアクションを取っていない |
| `edits` | 編集履歴を取っていない（現在の本文のみ） |

## 既知の制約

Slack の検索は、完全一致も全件も保証しない。確実に取れるのはチャンネル指定での取得であり、メンションの収集はその補助と考える。

private チャンネルは、参加していないと読めない。権限エラーになった対象はスキップし、理由を残す。

ワークスペースが複数ある場合、どのワークスペースを読むかは MCP の接続先で決まる。取り違えても結果からは気付きにくいので、どのワークスペースを見たかを報告に含める。
