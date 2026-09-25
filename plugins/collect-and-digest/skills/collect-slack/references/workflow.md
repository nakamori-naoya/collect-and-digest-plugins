# Slack保存工程

発言は、保存先のバケットに分けて書く。チャンネルの投稿はチャンネルIDのバケットへ、直接メンション、グループメンション、本人の発言から見つけたスレッドは `thread-<channel_id>-<thread_tsの数字>` のバケットへ入れる。

発言は1行1 JSONで一時ファイルへ書く。`ts` と `permalink` は必須で、本文は整形しない。

```jsonl
{"ts":"1723526400.000100","user":"U123","text":"…","permalink":"https://…","matched":"mention_direct"}
```

```bash
python3 scripts/message.py append --config "$CONFIG" \
  --operation-id <planのoperation.id> --bucket <planのbucket> \
  --target-date <YYYY-MM-DD> --messages-file /tmp/msgs.jsonl \
  --label "#dev" --url "https://<workspace>.slack.com/archives/<channel>" \
  --thread-ts "<thread_ts>" --thread-permalink "<親のpermalink>" \
  --omitted "files,reactions"
```

`ts`で統合して時系列に並べる。同tsの編集は旧レコードを`versions`へ保持する。明示的な削除通知は`{"ts":"...","permalink":"...","deleted":true}`として渡し、保存済み本文を保持したtombstoneにする。入力に無いだけのレコードは保持する。各実行で指定対象日の全範囲（スレッドは取得可能な全返信）を再取得する。指定外の過去日は更新しない。APIが返さない編集・削除は反映できず、現行snapshotの保証はしない。保存directoryの排他とredo journalで本文・台帳を同期し、中断後は次のcheck/append時に回復する。

## 既知の認証情報フォーマットの自動redaction

`collect.credential_redaction`（既定`true`）が有効なとき、`message.py append`は取得した各メッセージの本文を、既知の認証情報フォーマットに機械的・決定的に一致するかどうかだけで検査する。本文の意味を読んで、機密かどうかを見極めることはしない。

一致するフォーマット: PEM秘密鍵ヘッダー（`-----BEGIN ... PRIVATE KEY-----`）、GCPサービスアカウントJSONの鍵の組（`"type":"service_account"` + `"private_key"` + `"client_email"` が揃う）、AWS Access Key ID（`AKIA[0-9A-Z]{16}`）、GitHub/Slackのトークン形式。

一致したメッセージは、その1件だけ本文を`[REDACTED: possible credential material — see original]`へ差し替え、`permalink`はそのまま残す（`permalink`は元々必須なので消えない）。この判定は1メッセージの中で完結する決定的な処理なので、一致してもスキャンを止めず、利用者へ確認も求めず、他のメッセージと他のバケットの処理を続ける。

これは禁止事項の「伏せ字をしない」に対するただ一つの例外である。「これは機密っぽい」という意味の判断で伏せることはしない。意味の判断には検出漏れが避けられず、伏せたから安全だという誤った安心を与えるからである。ここで行うのは固定フォーマットへの文字列一致だけで、判断も停止も挟まないので、意味で伏せる処理とは別物である。

一致したメッセージが1件以上あるバケットは、front matterの`redacted`が`true`になる。`message.py append`の出力`counts.credential_redacted`がそのバケットでの一致件数であり、SKILLはこれを合算して報告する。

## 禁止事項

- 要約・抽出・分類をしない。
- 意味的な判断による伏せ字はしない（既知の認証情報フォーマットへの機械的一致だけは上記のとおり例外）。
- Slackへ書き込まない。
- git管理下へ保存しない。
- 設定で無効な対象を取得しない。
