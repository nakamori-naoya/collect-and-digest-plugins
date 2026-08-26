# Slack保存工程

| 対象 | バケット |
|---|---|
| チャンネル投稿 | チャンネルID |
| 直接・グループメンション・本人発言から見つけたスレッド | `thread-<channel_id>-<thread_tsの数字>` |

発言は1行1 JSONで一時ファイルへ書く。`ts` と `permalink` は必須で、本文は整形しない。

```jsonl
{"ts":"1723526400.000100","user":"U123","text":"…","permalink":"https://…","matched":"mention_direct"}
```

```bash
python3 "${PLUGIN_ROOT}/scripts/message.py" append --config "$CFG_FILE" \
  --operation-id <planのoperation.id> --bucket <planのbucket> \
  --target-date <YYYY-MM-DD> --messages-file /tmp/msgs.jsonl \
  --label "#dev" --url "https://<workspace>.slack.com/archives/<channel>" \
  --thread-ts "<thread_ts>" --thread-permalink "<親のpermalink>" \
  --omitted "files,reactions"
```

`ts`で重複を除き、時系列に並べる。同じ日に何度実行しても差分だけが増える。

## 既知の認証情報フォーマットの自動redaction

`collect.credential_redaction`（既定`true`）が有効なとき、`message.py append`は取得した各メッセージの本文を、既知の認証情報フォーマットに機械的・決定的に一致するかどうかだけで検査する。**解釈や見極めはしない。**

一致するフォーマット: PEM秘密鍵ヘッダー（`-----BEGIN ... PRIVATE KEY-----`）、GCPサービスアカウントJSONの鍵の組（`"type":"service_account"` + `"private_key"` + `"client_email"` が揃う）、AWS Access Key ID（`AKIA[0-9A-Z]{16}`）、GitHub/Slackのトークン形式。

一致したメッセージは、その1件だけ本文を`[REDACTED: possible credential material — see original]`へ差し替え、`permalink`はそのまま残す（`permalink`は元々必須なので消えない）。**この判定は1メッセージ単位で完結する決定的処理であり、一致してもスキャンを止めず、利用者へ確認も求めない。** 他のメッセージ・他のバケットの処理はそのまま続く。

これは禁止事項の「伏せ字をしない」に対する例外である。「これは機密っぽい」という**意味的な判断**はしない（検出漏れが必ずあり、偽の安心を売ることになるため）。ここでやるのは、固定フォーマットへの**文字列一致**だけであり、判断や停止を挟まない点で意味的redactionとは別物である。

一致したメッセージが1件以上あるバケットは、front matterの`redacted`が`true`になる。`message.py append`の出力`counts.credential_redacted`がそのバケットでの一致件数であり、SKILLはこれを合算して報告する。

## 禁止事項

- 要約・抽出・分類をしない。
- 意味的な判断による伏せ字はしない（既知の認証情報フォーマットへの機械的一致だけは上記のとおり例外）。
- Slackへ書き込まない。
- git管理下へ保存しない。
- 設定で無効な対象を取得しない。
