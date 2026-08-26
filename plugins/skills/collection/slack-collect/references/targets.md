# 何を対象にでき、どう取るか

対象は設定 `collect.targets` で個別に on/off する。resolverが`collection_plan.operations`へMCP操作を展開する。**計画に無い操作は実行しない。**

## チャンネル範囲

`collect.channels`は必ず次のどちらかを明示する。

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

未指定や空配列は許さない。`all`は全チャンネルの全投稿を取る指定ではない。`all`では`channel_messages: false`を必須とする。

## 設定からMCP実行計画への展開

| 設定 | 追加される操作 |
|---|---|
| `direct_mentions: true` | 本人解決 → 直接メンション検索 |
| `authored_threads: true` | 本人解決 → 本人発言検索 |
| `group_mentions: true` | `groups` 1件ごとのグループメンション検索 |
| `channel_messages: true` | `channels` 1件ごとのチャンネル読み取り |
| メンション・本人発言検索のいずれか | 出力を合流・重複排除し、発見したthreadごとに読み取り |

操作の`tool`、`arguments`、`foreach`が実行契約である。`{target_date}`、`{authenticated_user_id}`、`{thread_ref.*}`だけを実行時に置換する。検索条件やチャンネル制限をエージェントが再解釈しない。

## 使う MCP

| 用途 | ツール |
|---|---|
| チャンネルの読み取り | `slack_read_channel` |
| スレッドの読み取り | `slack_read_thread` |
| 検索（自分に関わるメンション） | `slack_search_public_and_private`（無ければ `slack_search_public`） |
| 発言者の解決 | `slack_read_user_profile` |
| リンクの取得 | 各メッセージの `permalink`。**取れないものは収集しない** |
| チャンネル名の解決 | `slack_search_channels` |

**送信系（`slack_send_message` ほか）は使わない。** この skill は read only。

## 対象日で絞る

Slack の `ts` は epoch 秒。対象日の設定timezoneにおける00:00と翌日00:00を境界にする。DSTがある日は24時間とは限らない。

```bash
python3 "${PLUGIN_ROOT}/scripts/date-range.py" --date "$DATE" --timezone "$(yq -er '.timezone' "$CFG_FILE")"
```

検索クエリで絞るときは `on:` / `after:` / `before:` を使う。取得後も **`ts` が範囲内かを必ず確認する**（検索は前後を含めて返すことがある）。

---

## `channel_messages` — 指定チャンネルの投稿

設定の `collect.channels` が配列のときだけ、列挙順に処理する。**数に制限はない。** `all`との組み合わせはresolverが拒否する。

```yaml
collect:
  channels:
    - C079CDA9H7F                      # ID だけでよい
    - id: C072N1VPETD
      label: "#dev"                    # 表示名を付けたい場合
```

- ID が分からない場合は `slack_search_channels` で解決してから使う。**推測で ID を作らない。**
- 1チャンネル = 1バケット。バケット名はチャンネル ID。
- 検索で見つけた親メッセージは `slack_read_thread` で返信まで辿る。返信は `thread_ts` を入れて同じバケットへ入れる。
- **すべてのメッセージに `permalink` を付ける。** 欠けていると書き込みが拒否される。

**チャンネルが多いときは1つずつ完了させる。** 全部取ってからまとめて書くと、途中で失敗したときに何も残らない。

---

## `direct_mentions` / `group_mentions` / `authored_threads` — 自分が関わったスレッド

**収集の単位はメッセージではなくスレッドである。**

**スレッドのどこか1回でも自分に関わるメンションがあれば、そのスレッド全体が対象になる。** 自分が発言していなくても、自分宛のメンションが1件あれば、そのスレッドの**全メッセージ**を取る。

理由は、断片だけ集めても読めないからである。「@自分 これどう思う？」だけを保存しても、何の話か分からない。**前後の文脈ごと持って初めて資料の素材になる。**

### 手順

**① 自分に関わる発言を検索で拾う。**

| 何を拾うか | どう拾うか |
|---|---|
| 自分宛の直接メンション | 認証ユーザー自身への `@メンション` |
| 自分が属するグループ宛 | `collect.groups` に列挙されたグループ宛。**自動判定できないので設定に書く** |
| 自分の発言 | 認証ユーザー自身が投稿したメッセージ。返信先を含むスレッド全体を対象にする |

`group_mentions: true`では`collect.groups`に`id`を持つobjectを1件以上要求する。空ならresolverが停止する。

**② ヒットしたメッセージから `thread_ts` を集める。**

- `thread_ts` があればそれを使う
- 無ければ、そのメッセージ自身がスレッドの親（`ts` を `thread_ts` として扱う）

**重複を除く。** 同じスレッドに自分宛のメンションが3回あっても、スレッドは1つである。

**③ 各スレッドを全文取る。**

`slack_read_thread` で親から末尾まで取る。**対象日で絞らない。** スレッドは日をまたぐので、対象日で切ると会話が途中で切れる。

対象日で絞るのは**②の検索まで**である。「その日に自分宛のメンションがあったスレッド」を、**全文**で取る。

**④ スレッドごとに1バケット。**

バケット名は `thread-<チャンネルID>-<thread_ts の数字部分>`。

```
slack/2026-08-14/thread-C123-1723526400000100.md
```

### 何を必ず持つか

**すべてのメッセージに `permalink` を付ける。** 欠けていると `message.py` が書き込みごと拒否する。あとから発言へ戻れない写しは作らない。

front matter には**チャンネルと当該リンクをタグとして静的に持つ**。

```yaml
tags: ["channel:C123", "channel-name:#dev", "link:https://<ws>.slack.com/archives/C123/p1723526400000100"]
thread_ts: "1723526400.000100"
thread_permalink: "https://<ws>.slack.com/archives/C123/p1723526400000100"
```

**本文を読み直さなくても、front matter だけでチャンネル別・スレッド別に束ねられる。**

`matched` には、そのスレッドが対象になった理由（`mention_direct` / `mention_group` / `authored_by_me`）を入れる。

---

## 落ちるもの（`omitted` へ記録する）

| 値 | 意味 |
|---|---|
| `files` | 添付ファイルを落としていない（リンクのみ） |
| `reactions` | リアクションを取っていない |
| `edits` | 編集履歴を取っていない（現在の本文のみ） |

---

## 既知の制約

- **検索の網羅性は保証されない。** Slack の検索は完全一致・全件を保証しないため、チャンネル指定での取得のほうが確実。メンション収集は補助と考える。
- **private チャンネルは参加していないと読めない。** 権限エラーはスキップして理由を残す。
- **ユーザーグループの所属は API から自動判定していない。** 設定の列挙が正本。
- ワークスペースが複数ある場合、MCP の接続先が正本。**どのワークスペースを見ているかを報告に含める。**
