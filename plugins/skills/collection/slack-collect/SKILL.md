---
name: collect-slack
description: 設定timezone上の対象日（既定は今日）の Slack を集めて保存する。設定から生成されたMCP実行計画に従い、全チャンネルまたは明示した複数チャンネルから、直接メンション・グループメンション・本人発言・通常投稿を明示的に選んで取る。要約も抽出もしない。「Slack を集めて」「今日の Slack を取り込んで」と言われたときに使う。
---

# collect-slack（Slack の収集）

対象日に属する発言を、原文のまま `slack_dir/<対象日>/` へ落とす。**抽出・要約・意味的な伏せ字はしない。** サマリや資料化はこのskillの責務ではない。正本は常に Slack。ここに置くのはその写しであり、書き戻す動線は作らない。

例外は1つだけ。既知の認証情報フォーマット（PEM秘密鍵、GCPサービスアカウントJSON、AWS Access Key IDなど）へ機械的に一致したメッセージは、`${.collect.credential_redaction}`が`true`のとき判断・停止・確認を挟まずその場で1件だけ本文を`permalink`と固定注記へ差し替え、収集を続ける。意味的な機密判断ではなく決定的なパターン一致で、詳細は[保存工程](references/workflow.md)に従う。

## 0. プラグイン root を決める

<!-- BEGIN shared:skill-entry/root-block -->
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
```

`PLUGIN_ROOT`は配布物rootの絶対パスである。単一skill pluginではこの`SKILL.md`があるdirectory、複数skill pluginでは`skills/<skill>/`の2つ上に当たる。Claude Codeでは`${CLAUDE_PLUGIN_ROOT}`が自動展開される。
<!-- END shared:skill-entry/root-block -->

## 1. 設定を解決する

<!-- BEGIN shared:skill-entry/config-load -->
```bash
CFG_FILE=$(bash "${PLUGIN_ROOT}/scripts/prepare.sh" "$(pwd)") || exit 2
trap 'rm -f "$CFG_FILE"' EXIT
```

**このコマンドは説明例ではない。必ず実行する。** 解決済みYAMLが空なら先へ進まない。設定ファイルを直接読んで代用しない。

本文中の `${...}` は解決済みYAMLのプロパティである。使用時に `yq -er` で読み、欠落または `null` なら停止する。
<!-- END shared:skill-entry/config-load -->

`${.instructions.collection.directive}` に従い、`${.slack_dir}` / `${.timezone}` / `${.collection_plan.operations}` を使う。**計画に無いMCP操作は実行しない。**

## 2. 対象日を決める

- 既定は`${.timezone}`の当日（`TZ="$(yq -er '.timezone' "$CFG_FILE")" date +%F`）。
- 利用者が `--date 2026-08-12` と指定したらそれを使う。
- ディレクトリのキーは**対象日**であって起動日ではない。

## 3. MCP実行計画を順番どおり実行する

`${.collection_plan.operations}` を配列順に実行する。`{target_date}`、`{target_start_ts}`、`{target_end_ts}`を対象日から確定し、本人解決の出力で`{authenticated_user_id}`を置換する。`inputs`は指定された出力を合流し、`foreach`はproducer付き参照の1件ごとに実行する。

ツールと引数の意味は[対象別の収集方法](references/targets.md)、保存形式は[保存工程](references/workflow.md)に従う。MCP未接続・権限不足はその操作だけをスキップして理由を記録する。**計画をLLM判断で追加・削除・並べ替えしない。**

## 4. 取る前に判定する

```bash
python3 "${PLUGIN_ROOT}/scripts/message.py" check --config "$CFG_FILE" \
  --operation-id <planのoperation.id> --bucket <planのbucket> \
  --target-date <YYYY-MM-DD> --latest-ts <そのバケットの最新 ts>
```

| decision | すること |
|---|---|
| `new` / `updated` | 本文を取得して書く |
| `unchanged` | 何もしない |
| `recheck` | 最新 ts が取れないので取得して突き合わせる |

## 5. 書き込む

取得した発言を1行1 JSONの一時ファイルへ書き、[保存工程](references/workflow.md)のappendコマンドへ渡す。スクリプトが重複排除、整列、front matter、台帳更新を行う。

## 6. 報告する

| 項目 | 内容 |
|---|---|
| 対象日 | 判定に使った日付 |
| バケットごとの件数 | 新規追加 / 総数 |
| credential-redacted | 既知の認証情報フォーマットに一致して本文を差し替えた件数（`message.py append`の`counts.credential_redacted`を合算） |
| スキップ | 対象と理由（MCP 未接続、権限なし、設定で無効） |
| 保存先 | `slack_dir/<対象日>/` |

0件でも「0件だった」と報告する。**黙って終わらない。**

禁止事項は[保存工程](references/workflow.md)に従う。
