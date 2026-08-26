---
name: make-session-digest
description: session-collectの非公開索引を使い、対象日に活動したClaude Code / CodexセッションごとのIDと短い要約を1本の日次記録へ保存する。「今日のエージェント作業をまとめて」「セッションを日報にして」「session digest」と依頼されたときに使う。
---

# make-session-digest（日次セッション記録）

セッション原文を複製せず、対象日に活動したセッションごとの不透明IDと短い要約を1本のMarkdownへ保存する。

## 0. プラグイン root を決める

<!-- BEGIN shared:skill-entry/root-block -->
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
```

`PLUGIN_ROOT`は配布物rootの絶対パスである。単一skill pluginではこの`SKILL.md`があるdirectory、複数skill pluginでは`skills/<skill>/`の2つ上に当たる。Claude Codeでは`${CLAUDE_PLUGIN_ROOT}`が自動展開される。
<!-- END shared:skill-entry/root-block -->

## 1. 設定を読み込む

<!-- BEGIN shared:skill-entry/config-load -->
```bash
CFG_FILE=$(bash "${PLUGIN_ROOT}/scripts/prepare.sh" "$(pwd)") || exit 2
trap 'rm -f "$CFG_FILE"' EXIT
```

**このコマンドは説明例ではない。必ず実行する。** 解決済みYAMLが空なら先へ進まない。設定ファイルを直接読んで代用しない。

本文中の `${...}` は解決済みYAMLのプロパティである。使用時に `yq -er` で読み、欠落または `null` なら停止する。
<!-- END shared:skill-entry/config-load -->

`${.instructions.execution.directive}` / `${.playbook.output.dir}` / `${.playbook.output.timezone}` / `${.playbook.output.max_chars_per_session}` / `${.playbook.output.subagents}` / `${.playbook.steps}`に従う。

**各工程を呼ぶときは `--scope=${.resolution.scope_root}` を必ず渡す。**この段取りを通るときだけ効く設定がそこにある。入れ子の段取りへは受け取ったscopeをそのまま渡し、自分の名前で作り直さない。

## 2. 工程を実行する

解決済み`${.playbook.steps}`を上から実行し、needsが揃わない工程は開始しない。collectがpartialまたはprovisionalを返したら停止し、日次資料を作らない。

material工程ではsession-collectが返したday indexを次へ渡す。

```bash
python3 "${PLUGIN_ROOT}/scripts/material.py" \
  --day-index <非公開日別索引> --date <YYYY-MM-DD> \
  --out-dir <非公開一時directory>
```

`${.playbook.output.subagents}`が`include`のときだけ`--include-subagents`を付ける。

## 3. 要約する

material内の`source_path`は要約時だけ読む。全文や中間要約を保存しない。何を残し、何を混入させないかは[privacy境界](references/privacy.md)、本文・metadata・タグの形は[日次記録の契約](references/output.md)に従う。1セッションの本文は`${.playbook.output.max_chars_per_session}`以内とし、超過時はtruncateせず書き直す。

成果物は`<output.dir>/<対象日>.md`。既存内容のinput hashが変わる場合は黙って上書きせず、明示的なforceを要求する。0件では空の成果物を書かない。

storeへ本文とmetadataの2ファイルを渡す。metadataの検証状態は実際に確認したものだけ`passed`とし、未確認を成功扱いしない。
