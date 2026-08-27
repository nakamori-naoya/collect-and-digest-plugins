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

`${.instructions.execution.directive}` / `${.playbook.output.dir}` / `${.playbook.output.timezone}` / `${.playbook.output.max_chars_per_session}` / `${.playbook.output.subagents}` / `${.playbook.contract}` / `${.playbook.steps}`に従う。資料化と保存は`${.deps.write-doc.root}`のplaybookを使い、このskillから`writing-rules`や`doc-render`を直接呼ばない。

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

## 3. write-docへ資料化を委譲する

material内の`source_path`は要約時だけ読む。全文や中間要約を保存しない。何を残し、何を混入させないかは[privacy境界](references/privacy.md)、本文・metadata・タグの形は[日次記録の契約](references/output.md)に従う。1セッションの本文は`${.playbook.output.max_chars_per_session}`以内とし、超過時はtruncateせず書き直す。

`${.playbook.contract.document_type}`を指定済みの型、上記2つのreferenceを追加指示、materialのitemsを素材として`write-doc`を実行する。`output_format`は`${.playbook.output.format}`、出力directoryは`${.playbook.output.dir}`、ファイル名は`${.playbook.contract.output_name}`の`<target_date>`を対象日へ置換した値として渡す。型を選び直させず、別の資料化工程を挟まない。

成果物は`<output.dir>/<対象日>.md`。既存資料がある場合は、`write-doc`の上書きguardに従ってまず既存を読み、front matterの`input_hash`を比較する。同じなら変更せず終了し、異なるなら利用者からその既存pathの更新が明示されている場合だけ`update_target`として`write-doc`へ渡す。独自の保存scriptやforceオプションは使わない。0件では空の成果物を書かない。

資料化が完了したらmaterialを削除する。最終Markdown以外の本文ファイルやmetadataファイルを永続化しない。
