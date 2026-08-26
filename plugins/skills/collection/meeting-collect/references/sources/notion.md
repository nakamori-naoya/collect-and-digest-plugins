# ソース: Notion 議事録

## 使う MCP

| 用途 | ツール |
|---|---|
| 一覧 | `notion-query-meeting-notes` |
| 本文 | `notion-fetch`（議事録ページ ID を渡す） |

`notion-query-meeting-notes` は既定で**認証ユーザーが参加者または作成者の議事録**を返す。current-user のフィルタを足す必要はない。最大50件。

## 対象日で絞る

`last_edited_time` または `created_time` の date filter を使う。対象日が今日なら `date_is` に `today`（相対）を使い、過去日なら `exact` の `date` を渡す。

一覧の結果から次を取る。

| front matter | 取得元 |
|---|---|
| `source_id` | ページ ID |
| `url` | ページ URL |
| `title` | 会議名 |
| `occurred_at` | 議事録の日時プロパティ。無ければ `created_time` |
| `attendees` | attendees プロパティ（**上流の生値**。内外の分類はしない） |
| `source_updated_at` | `last_edited_time` |
| `props` | DB プロパティの生ダンプ |

## 本文

`notion-fetch` の返す markdown を**そのまま**本文にする。見出しの整形も要約もしない。

## 落ちるもの（`omitted` へ記録する）

| 値 | 意味 |
|---|---|
| `comments` | ページ内コメントを取っていない（既定 OFF） |
| `images` | 画像を落としていない（リンクのみ） |
| `child_pages` | 子ページを取っていない（リンクのみ） |

## 既知の制約

- **添付・画像の署名付き URL は約1時間で失効する。** このskillはasset保存を実装していない。リンクだけを残し、`omitted: [images]`として表明する。
- 子ページは再帰が非有界なので追わない。子ページ自身が議事録なら、それは自分のクエリで独立に収集される。
- MCP が未接続なら収集をスキップし、理由を報告に残す。**止めない。**
