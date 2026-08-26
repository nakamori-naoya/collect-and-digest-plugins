# meeting-collect — 設定リファレンス

対象日（JST）に属する Notion / Google Docs の議事録を、**原文のまま**1箇所へ集める。抽出も要約もしない。

設定候補は3箇所に置けるが、**混ぜない。最上位の1ファイルだけを使う。**

| 層 | ファイル | 持つもの | commit するか |
|---|---|---|---|
| リポジトリ | `<repo>/.harness-plugins/meeting-collect.config.yml` | 完全な収集設定 | する |
| 個人 | `~/.config/harness-plugins/meeting-collect.config.yml` | 完全な収集設定 | しない |
| 実行時状態 | `notes_dir` 配下 | 収集した議事録と台帳 | しない（**git 管理外**） |

優先順位は**repository > personal > bundled defaults**。存在する最上位の1ファイルだけを選び、値を混ぜない。

---

## `<repo>/.harness-plugins/meeting-collect.config.yml`

```yaml
version: 1
notes_dir: ~/meeting-notes
timezone: Asia/Tokyo

collect:
  sources:
    notion:
      enabled: true
    google_docs:
      enabled: true
      drive_query: "Notes by Gemini"
  transcript: true
  max_bytes: 10485760
instructions:
  collection:
    directive: 有効なソースから対象日の議事録を原文のまま収集し、要約・伏せ字・truncationをしない
```

| キー | 型 | 既定 | 説明 |
|---|---|---|---|
| `version` | number | — | 設定の版。現在は `1` |
| `notes_dir` | path | `~/meeting-notes` | 収集先。`~` を展開する。**git 管理下は拒否される**（後述） |
| `timezone` | string | `Asia/Tokyo` | 対象日の判定に使うタイムゾーン |
| `collect.sources.notion.enabled` | bool | `true` | Notion 議事録を集めるか |
| `collect.sources.google_docs.enabled` | bool | `true` | Google Docs（Gemini 議事録）を集めるか |
| `collect.sources.google_docs.drive_query` | string | なし | Drive 検索の絞り込みに使う手掛かり |
| `collect.transcript` | bool | `true` | 文字起こしを `.transcript.md` として別ファイルで取るか |
| `collect.max_bytes` | number | `10485760` | 単一文書の上限。超えたら**エラーで中断**し、部分ファイルを書かない |

### `notes_dir` の制約（機械強制）

判定軸は **gitignore されているか** の一点。書き込み前に検査し、条件を満たさなければ**警告ではなく拒否**する（exit 2）。

| `notes_dir` の場所 | 結果 |
|---|---|
| git 管理の外（`~/meeting-notes` など） | ✅ 通る |
| リポジトリ内だが **gitignore されている** | ✅ 通る |
| リポジトリ内で gitignore されていない | ⛔ 拒否 |

**既定は git 管理の外を推奨する。** リポジトリ内に置くなら `.gitignore` へ足せばよいが、ignore を外した瞬間に議事録が commit 対象になる。管理外なら、その事故が構造的に起きない。

議事録には人事・報酬・顧客名が入りうる。commit される経路を構造的に断つための不変条件であり、設定で緩められない。

`~/Documents/` 配下も避けたほうがよい。macOS の TCC により launchd から読めず、定期実行のような headless なジョブが書き込めなくなる。

---

## `~/.config/harness-plugins/meeting-collect.config.yml`

形式は`.harness-plugins/meeting-collect.config.yml`と同じ完全な設定である。repository設定が無い場合だけ選ばれる。

---

## 収集物の形（実行時状態）

```text
<notes_dir>/
  index.jsonl                                  # 収集台帳。冪等判定の正本
  2026-08-13/                                  # 対象日（起動日ではない）
    notion-{page_id}.md
    notion-{page_id}.transcript.md
    google_docs-{file_id}.md
```

### front matter（`schema: 1`）

**手で書かない。** スクリプトが組み立てる。

| キー | 説明 |
|---|---|
| `schema` | 契約の版 |
| `source` | `notion` / `google_docs` |
| `source_id` | 上流の一意 ID |
| `url` / `title` | 上流のもの |
| `occurred_at` | 会議の開催日時。取れなければ `null`。**推定して埋めない** |
| `attendees` | 上流の生値の配列。内外の分類はしない |
| `recording_url` | 録画 URL のみ。動画本体は取らない |
| `fetched_at` | 取得時刻 |
| `source_updated_at` | **更新検知の一次キー**（上流自身が持つ更新時刻） |
| `content_hash` | 変換後本文の sha256。二次の確認に使う |
| `collector` | 変換器のバージョン。hash が一斉に変わったときの切り分け用 |
| `fidelity` | 常に `markdown-lossy` |
| `omitted` | 見えたが取らなかったもの（`comments` / `images` / `child_pages` など） |
| `parts.transcript` | 文字起こしファイル名（あれば） |
| `props` | Notion の DB プロパティ生ダンプ |

### 下流の読み方

> **`part:` キーを持たないファイルだけを既定で読む。文字起こしが要るときだけ `parts:` を辿る。**

この一行で、資料化側は数万字の文字起こしから既定で守られ、必要なときだけ機械的に到達できる。

### `index.jsonl`

1行1レコードの append-only。

```json
{"ts":"...","source":"notion","source_id":"...","source_updated_at":"...","content_hash":"sha256:...","path":"...","target_date":"2026-08-13","title":"..."}
```

冪等判定は `(source, source_id)` で同一性、`source_updated_at` → `content_hash` の順で変更検知。

---

## 秘密について

**このプラグインは秘密を1つも必要としない。** Notion と Google Drive は claude.ai のコネクタで引くため、認証は Claude アカウント側にある。プラグインもリポジトリもトークンを持たない。

stdio MCP サーバへ切り替える場合は、`plugin.json` の `mcpServers` で**宣言だけ**を持ち、値は環境から渡す。

```json
{ "mcpServers": { "notion": {
  "command": "npx", "args": ["-y", "@notionhq/notion-mcp-server"],
  "env": { "NOTION_TOKEN": "${NOTION_TOKEN}" } } } }
```

なお、この構成でいちばん秘密度が高いのは設定ではなく**収集した議事録そのもの**である。だから `notes_dir` を git 管理外に置き、書き込み前に検査する。

---

## やらないこと（設定で変えられない）

- **秘匿の伏せ字をしない。** 意味的判断であり検出漏れが必ずある。内容を書き換えると `content_hash` と忠実度の宣言が壊れる。
- **truncation をしない。** 途中で切れた写しは「無い」より悪い。上限超過はエラーで止める。
- **忠実だと言い切らない。** markdown 化で落ちるものがあるため `fidelity: markdown-lossy` を常時宣言し、`omitted` に列挙する。
- **子ページを再帰しない。** 非有界になる。リンクのみ。

---

## 未確認

- Gemini 議事録が、要約と文字起こしを同一 Doc の別セクションで持つのか、別ファイルなのかは実物で未確認。
- Notion の添付・画像の署名付き URL は約1時間で失効する。既定（リンク温存）ではリンク切れが確定する。
