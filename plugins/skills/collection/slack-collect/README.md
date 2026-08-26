# slack-collect — 設定リファレンス

設定timezone上の対象日の Slack を集める。**何を対象にするかは設定で選ぶ。**

| 層 | ファイル | 持つもの | commit するか |
|---|---|---|---|
| リポジトリ | `<repo>/.harness-plugins/slack-collect.config.yml` | どのチャンネル・どの対象を集めるか | する |
| マシン（個人） | `~/.config/harness-plugins/slack-collect.config.yml` | 個人設定 | しない |
| 実行時状態 | `slack_dir` 配下 | 収集した発言と台帳 | しない（**gitignore 必須**） |

優先順位は**repository > personal > bundled defaults**。最上位の1ファイルだけを選び、配列を含めて値を一切マージしない。選ばれる設定は全必須キーを持つ。

---

## `<repo>/.harness-plugins/slack-collect.config.yml`

```yaml
version: 1
slack_dir: slack            # 相対パスはリポジトリ root 基準
timezone: Asia/Tokyo

collect:
  channels: all             # 本人関連を全チャンネルから探す。全投稿は取らない
  targets:
    channel_messages: false # allでは必ずfalse
    direct_mentions: true   # 自分宛の直接メンション
    group_mentions: false  # collect.groupsのグループ宛メンション
    authored_threads: true # 自分の発言を含むスレッド
  groups:                   # group_mentionsを使うならID必須
    - id: S01234567
      label: "@dev-team"
  max_bytes: 10485760
  credential_redaction: true # 既知の認証情報フォーマットに一致した1件だけ本文を差し替える
instructions:
  collection:
    directive: 有効な対象のSlack発言を原文のまま収集し、要約・伏せ字・Slackへの書き込みをしない
```

| キー | 型 | 既定 | 説明 |
|---|---|---|---|
| `slack_dir` | path | `slack` | 収集先。**git 管理下は gitignore されていないと拒否される** |
| `timezone` | string | `Asia/Tokyo` | 対象日の判定に使う |
| `collect.channels` | `all`または非空array | `all` | `all`は本人関連をチャンネル制限なしで検索。arrayは文字列IDまたは`id`/`label` objectを複数指定 |
| `collect.targets.channel_messages` | bool | `false` | 列挙チャンネルの全投稿を集めるか。`channels: all`では必ずfalse |
| `collect.targets.direct_mentions` | bool | `true` | 自分宛の直接メンションからスレッドを探す |
| `collect.targets.group_mentions` | bool | `false` | `groups`の各ID宛メンションからスレッドを探す。trueなら1件以上必須 |
| `collect.targets.authored_threads` | bool | `true` | 自分の発言からスレッドを探す |
| `collect.groups` | array | `[]` | 自分が属するユーザーグループ。**API から自動判定していない** |
| `collect.max_bytes` | number | `10485760` | 1バケットの上限。超えたらエラーで中断 |
| `collect.credential_redaction` | bool | `true` | 既知の認証情報フォーマット（PEM秘密鍵・GCPサービスアカウントJSON・AWS Access Key ID など）に機械的に一致した1メッセージだけ、本文をpermalinkと固定注記へ差し替える。詳細は[秘匿](#秘匿) |

個人設定を使う場合も同じ完全な形式で書く。repository設定が存在すれば個人設定は読まれない。

複数チャンネルへ制限する場合は、`all`の代わりに非空配列を明示する。

```yaml
collect:
  channels:
    - C079CDA9H7F
    - id: C072N1VPETD
      label: "#dev"
  targets:
    channel_messages: true
    direct_mentions: true
    group_mentions: false
    authored_threads: true
```

`channels`の未指定・空配列・未知の文字列はresolverが拒否する。resolverは設定から`collection_plan.operations`を生成し、skillはその配列順にMCPを実行する。

---

## 保存の形

```text
<slack_dir>/
  index.jsonl                    # 収集台帳
  2026-08-13/                    # 対象日
    C079CDA9H7F.md               # チャンネル1つ = 1ファイル
    thread-C123-1723526400000100.md # 関連スレッド1件
```

**バケット = 保存の単位**。1バケット1ファイルで、その日の発言が時系列で並ぶ。

### front matter（`schema: 1`）

| キー | 説明 |
|---|---|
| `source` | 常に `slack` |
| `source_id` | `<bucket>@<対象日>` |
| `bucket` / `label` | 保存単位と表示名 |
| `url` | チャンネルの URL |
| `target_date` | 対象日 |
| `fetched_at` | 取得時刻 |
| `message_count` / `last_ts` | 件数と最新のタイムスタンプ |
| `content_hash` | 変更検知 |
| `collector` / `fidelity` / `omitted` | 変換器・忠実度・落としたもの |
| `redacted` | このバケットに、既知の認証情報フォーマットへ機械的に一致して本文を差し替えたメッセージが1件でもあれば`true`。下流（digest等）はこれだけを見て機械的に検知できる |

### 冪等

各発言の直前に、生の JSON を HTML コメントで埋めてある。

```markdown
<!-- slack-msg {"ts":"1723526400.000100", …} -->
**14:20 naoya**  `channel`  [link](https://…)
```

再実行時はこれを読み戻して `ts` で突き合わせるので、**同じ日に何度実行しても重複しない**。差分だけが増える。見た目の整形を変えても壊れない。

---

## 秘匿

**Slack の発言には人事・報酬・顧客名・個人名が入りうる。** 収集物がいちばん秘匿度が高い。

- `slack_dir` が git 管理下かつ gitignore されていなければ、スクリプトが**書き込みを拒否**する（exit 2）。
- **意味的な伏せ字（redaction）はしない。** 「これは機密っぽい」という解釈は検出漏れが必ずあるため、偽の安心を売らない。秘匿は置き場とアクセス制御で解く。
- **ただし、既知の認証情報フォーマットへの機械的・決定的なパターン一致だけは例外として行う。** これは意味的判断ではない — PEM秘密鍵ヘッダー（`-----BEGIN ... PRIVATE KEY-----`）、GCPサービスアカウントJSONの鍵の組（`"type":"service_account"` + `"private_key"` + `"client_email"`）、AWS Access Key ID（`AKIA[0-9A-Z]{16}`）、GitHub/Slackのトークン形式など、固定フォーマットに一致するかどうかだけを見る。一致した1メッセージだけ、本文をそのまま保存せず`permalink`と固定注記（`[REDACTED: possible credential material — see original]`）へ差し替える。判断や停止を挟まず、その場で自動的に行い収集は止めない。既定は`collect.credential_redaction: true`（安全側）。front matterの`redacted`でバケット単位に機械検知できる。
- DMは実行可能なMCP経路が無いため対象外。旧`collect.targets.dm`が残っていればresolverが停止する。

トークンは要らない（Slack は claude.ai のコネクタ経由）。stdio MCP へ切り替える場合は `env` の `${VAR}` で環境から渡す。

---

## やらないこと

- 要約・抽出・分類（`doc-compose` の責務）
- Slack への書き込み（送信・リアクション・チャンネル作成）
- 設定で無効な対象の取得
- truncation（上限超過はエラーで中断し、部分ファイルを書かない）

---

## 既知の制約

- **検索の網羅性は保証されない。** メンション収集は補助と考え、確実さが要るならチャンネル指定を使う。
- **private チャンネルは参加していないと読めない。** 権限エラーはスキップして理由を残す。
- **ユーザーグループの所属は自動判定していない。** `collect.groups` の列挙が正本。
