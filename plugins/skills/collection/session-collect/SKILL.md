---
name: collect-sessions
description: Claude Code / Codex のローカルセッションを、原文を複製せず対象日に活動したセッションの非公開索引として収集する。「セッションを集めて」「今日のCodex作業を記録して」「collect-sessions」と依頼されたときに使う。
---

# collect-sessions（セッション索引の収集）

対象日に活動したClaude Code / Codexセッションを発見し、正本への参照と決定的メタデータだけを`${.state_dir}`へ保存する。原文、プロンプト、応答、tool入出力、system promptは複製しない。要約はこのskillの責務ではない。

## 0. プラグイン root を決める

<!-- BEGIN shared:skill-entry/root-block -->
```bash
BUNDLE_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
if [ -d "${BUNDLE_ROOT}/skills/collection/session-collect" ]; then
  PLUGIN_ROOT="${BUNDLE_ROOT}/skills/collection/session-collect"
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

`${.instructions.collection.directive}`に従い、`${.state_dir}` / `${.timezone}` / `${.sources}` / `${.collection}`を使う。

## 2. 対象日を決める

利用者指定がなければ`${.timezone}`の当日を使う。対象日はセッション開始日ではなく、その日にtimestampを持つイベントが存在するかの検索条件である。

## 3. 走査する

```bash
python3 "${PLUGIN_ROOT}/scripts/session.py" scan \
  --config "$CFG_FILE" --date <YYYY-MM-DD>
```

事前確認だけなら`--dry-run`を付ける。出力は`decision / reason / artifact / counts`の4キーを持つJSONである。

## 4. 停止条件

enabledなrootの欠落、中間の真にparse不能なJSONL、上限超過、索引破損、保存先の安全違反では停止する。末尾の書きかけだけは`provisional`として扱う。0件でもcountsを明示し、黙って終わらない。

セッションファイルが対象schema外（sessionId自体を持たないWorkflow journal.jsonl形式など）や、sessionIdはあるが有効なturn/timestampをまだ持たない空セッションは、停止条件ではない。1ファイルだけ理由付きでスキップし、走査は継続する（`counts.unrecognized`、私的な`artifact.skipped_log`）。

詳しい形式・privacy・更新規則は[セッション形式と収集契約](references/workflow.md)に従う。
