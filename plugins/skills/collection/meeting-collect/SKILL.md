---
name: collect-notes
description: Notion / Google Docs の議事録のうち、設定timezone上の対象日（既定は今日）に属するものを1箇所へ集めて保存する。要約も抽出もしない。「議事録を集めて」「collect-notes」「今日のミーティングノートを取り込んで」と言われたときに使う。
---

# collect-notes（議事録の収集）

対象日に属する議事録を、原文のまま `<notes_dir>/<対象日>/` へ落とす。**抽出・要約・秘匿の伏せ字は一切しない。** 資料化やチケット化はこのskillの責務ではない。

正本は常に上流（Notion / Google Docs）。ここに置くのはその写しであり、書き戻す動線は作らない。

## 0. プラグイン root を決める

<!-- BEGIN shared:skill-entry/root-block -->
```bash
BUNDLE_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
if [ -d "${BUNDLE_ROOT}/skills/collection/meeting-collect" ]; then
  PLUGIN_ROOT="${BUNDLE_ROOT}/skills/collection/meeting-collect"
else
  PLUGIN_ROOT="${BUNDLE_ROOT}"
fi
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

`${.instructions.collection.directive}` に従い、`${.notes_dir}` / `${.timezone}` / `${.collect.sources}` / `${.collect.transcript}` を使う。

## 2. 対象日を決める

- 既定は`${.timezone}`の当日。`TZ="$(yq -er '.timezone' "$CFG_FILE")" date +%F`で得る。
- 利用者が `--date 2026-08-12` のように指定したらそれを使う。
- ディレクトリのキーは**対象日**であって起動日ではない。0:30 に前日分を回収しても、前日のディレクトリへ入る。

## 3. 収集工程を実行する

[収集工程の詳細](references/workflow.md)を読み、有効なソースだけを処理する。`${.collect.sources.notion.enabled}`がtrueなら[Notionの収集方法](references/sources/notion.md)、`${.collect.sources.google_docs.enabled}`がtrueなら[Google Docsの収集方法](references/sources/google-docs.md)を読む。MCPが使えないソースは理由を記録してスキップする。

## 4. 1件ずつ、取る前に判定する

全文を取りに行く前に台帳と突き合わせる。無駄なフェッチと変換を避けるため。

```bash
python3 "${PLUGIN_ROOT}/scripts/note.py" check --config "$CFG_FILE" \
  --source notion --source-id <ID> --source-updated-at <上流の更新時刻>
```

判定結果ごとの動作とwriteコマンドは[収集工程の詳細](references/workflow.md)に従う。

## 5. 報告する

対象日、新規・更新・変更なし、スキップ理由、保存先を報告する。0件でも黙って終わらない。報告形式と収集上の禁止事項も[収集工程の詳細](references/workflow.md)に従う。
