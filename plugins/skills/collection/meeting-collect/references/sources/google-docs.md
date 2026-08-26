# ソース: Google Docs（Google Meet の Gemini 議事録）

## 使う MCP

| 用途 | ツール |
|---|---|
| 一覧 | `search_files`（Google Drive） |
| 本文 | `read_file_content` |
| 付随情報 | `get_file_metadata` |

## 対象日で絞る

Drive のクエリ構文で `mimeType` と時刻を指定する。日付は対象日の`${.timezone}` 0:00をUTCへ直して渡す。翌日境界も翌日のローカル0:00から求め、24時間固定にしない。

```text
mimeType = 'application/vnd.google-apps.document' and modifiedTime >= '<対象日 00:00 の UTC 表記>' and modifiedTime < '<翌日 00:00 の UTC 表記>'
```

議事録の絞り込みはタイトルの手掛かり（`Notes by Gemini` / `のメモ` / 会議名）を併用する。設定 `collect.sources.google_docs.drive_query` があればそれを優先する。

| front matter | 取得元 |
|---|---|
| `source_id` | Drive のファイル ID |
| `url` | `viewUrl` |
| `title` | ファイル名 |
| `occurred_at` | 会議の開催日時。取れなければ `createdTime` |
| `attendees` | 本文の参加者セクション（**上流の記載どおり**。補完・推定はしない） |
| `source_updated_at` | `modifiedTime` |

## 文字起こし

Gemini の議事録は、要約と文字起こしの入れ物が **同一 Doc の別セクションか、別ファイルか未確認**。実装時に実物で確認する。

- 同一 Doc の別セクションなら、見出し境界で機械的に分割し、文字起こし側を `--transcript-file` へ渡す。
- 別ファイルなら、そのファイルを独立に取得して `--transcript-file` へ渡す。

**いずれの場合も、分割は構造境界での機械的な振り分けに限る。** 内容を読んで取捨選択したらそれは抽出であり、この skill の責務ではない。

`collect.transcript: false` の設定、または `--no-transcript` 指定のときは取得しない。その場合は `omitted` へ `transcript` を足す。

## 落ちるもの（`omitted` へ記録する）

| 値 | 意味 |
|---|---|
| `comments` | Docs のコメントを取っていない |
| `images` | 埋め込み画像を落としていない |
| `suggestions` | 提案モードの差分を取っていない |

## 既知の制約

- markdown 変換でコメントのアンカー位置・セル結合は失われる。`fidelity: markdown-lossy` の宣言で表明する。
- 録画がある場合は `recording_url` に URL だけを入れる。**動画本体は取らない。**
- Drive が未接続なら収集をスキップし、理由を報告に残す。**止めない。**
