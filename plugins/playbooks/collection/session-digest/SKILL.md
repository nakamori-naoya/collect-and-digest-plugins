---
name: make-session-digest
description: session-collectの非公開索引を使い、対象日に活動したClaude Code / CodexセッションごとのIDと短い要約を1本の日次記録へ保存する。「今日のエージェント作業をまとめて」「セッションを日報にして」「session digest」と依頼されたときに使う。
---

# make-session-digest（日次セッション記録）

セッション原文を複製せず、対象日に活動したセッションごとの不透明IDと短い要約を1本のMarkdownへ保存する。

## 0. プラグイン root を決める

<!-- BEGIN shared:skill-entry/root-block -->
```bash
BUNDLE_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
if [ -d "${BUNDLE_ROOT}/playbooks/collection/session-digest" ]; then
  PLUGIN_ROOT="${BUNDLE_ROOT}/playbooks/collection/session-digest"
else
  PLUGIN_ROOT="${BUNDLE_ROOT}"
fi
```

`PLUGIN_ROOT`は配布物rootの絶対パスである。単一skill pluginではこの`SKILL.md`があるdirectory、複数skill pluginでは`skills/<skill>/`の2つ上に当たる。Claude Codeでは`${CLAUDE_PLUGIN_ROOT}`が自動展開される。
<!-- END shared:skill-entry/root-block -->

## 1. 設定を読み込む

<!-- BEGIN shared:skill-entry/config-load -->
```bash
CFG_FILE=$(bash "${PLUGIN_ROOT}/scripts/prepare.sh" "$(pwd)") || exit 2
```

**このコマンドは説明例ではない。必ず実行する。** 解決済みYAMLが空なら先へ進まない。設定ファイルを直接読んで代用しない。

本文中の `${...}` は解決済みYAMLのプロパティである。使用時に `yq -er` で読み、欠落または `null` なら停止する。
<!-- END shared:skill-entry/config-load -->

`${.instructions.execution.directive}` / `${.playbook.output.dir}` / `${.playbook.output.timezone}` / `${.playbook.output.max_chars_per_session}` / `${.playbook.output.subagents}` / `${.playbook.contract}` / `${.playbook.steps}`に従う。資料化と保存は依存先`write-doc`の公開playbookへ委譲する（手順は3節）。相手の中の作りを前提にせず、契約の入力・出力だけでやり取りする。

**各工程を呼ぶときは `--scope=${.resolution.scope_root}` を必ず渡す。**この段取りを通るときだけ効く設定がそこにある。入れ子の段取りへは受け取ったscopeをそのまま渡し、自分の名前で作り直さない。

## 2. 工程を実行する

解決済み`${.playbook.steps}`を上から実行し、needsが揃わない工程は開始しない。collectがpartialまたはprovisionalを返したら停止し、日次資料を作らない。

material工程ではsession-collectが返したday indexを次へ渡す。

```bash
python3 "${PLUGIN_ROOT}/scripts/material.py" \
  --day-index <非公開日別索引> --date <YYYY-MM-DD> \
  --out-dir ~/.local/state/harness-plugins/session-digest/material
```

`--out-dir`はrepository外の実行専用subdirectoryに固定する。HOME、TMPDIR root、共有directoryそのものは渡さない。

`${.playbook.output.subagents}`が`include`のときだけ`--include-subagents`を付ける。

## 3. write-docへ資料化を委譲する

material内の`source_path`は要約時だけ読む。全文や中間要約を保存しない。何を残し、何を混入させないかは[privacy境界](references/privacy.md)、本文・metadata・タグの形は[日次記録の契約](references/output.md)に従う。1セッションの本文は`${.playbook.output.max_chars_per_session}`以内とし、超過時はtruncateせず書き直す。

`document`工程で契約ID `write-doc/write-doc` の公開playbookへ、次の入力objectを直接渡す。入力YAML、解決済みYAML、依存先の`prepare.sh`、結果受取用ファイルは作らない。

- `material`: `material.py`が返した`material_path`を`{kind: file, path: <絶対path>}`にした1要素のobject配列
- `document_type`: `${.playbook.contract.document_type}`の値
- `output_directory`: `${.playbook.output.dir}`を展開した絶対path
- `name`: `${.playbook.contract.output_name}`の`<target_date>`を対象日へ置換した`.md`ファイル名
- `references`: `references/output.md`と`references/privacy.md`の読み取り可能な絶対path配列

新規作成では`output_directory`と`name`を必ず組にする。既存資料を同じpathへ更新すると利用者が明示した場合だけ、この2つに代えて`update_target`へ確認済みの絶対pathを渡す。両方式を同時に渡さない。

公開playbookが直接返した`status`を確認する。`completed`なら`path`をdocument工程の`path`として次へ渡す。`failed`なら`reason`を報告して停止し、資料が書けたことにしない。返却値に`path`と`reason`の両方がある場合や、契約にない値がある場合も停止する。

### 同じpathに既存資料があるとき

成果物は`<output.dir>/<対象日>.md`。同名の既存資料があるときは、**依頼する前に**こちらで既存を読み、front matterの`input_hash`を比較する。同じなら何も依頼せず終了する。異なり、かつ利用者からその既存pathの更新が明示されているときだけ、3-1で`update_target`にその絶対pathを書く。明示が無ければ資料化を依頼しない。独自の保存scriptやforceオプションは持たない。0件では空の成果物を書かない。

cleanupはdocumentが返した`path`とcollectが返した`index`、今回の`material_path`が揃った後にだけ最終stepとして実行する。3つの明示pathを`material.py --cleanup`へ渡す。

```bash
python3 "${PLUGIN_ROOT}/scripts/material.py" --cleanup \
  --material-path <material_path> --path <path> --index <index>
```

出力JSON全体を`cleanup_report`として扱う。cleanupはmaterial file 1件だけをunlinkし、0700の実行専用directoryは残す。

設定生成で返却された絶対pathを実行記録へ残す。別shellでは記録した絶対pathを `CFG_FILE` へ明示代入して読む。処理が成功・停止・失敗した最後に `python3 "${PLUGIN_ROOT}/scripts/run-config.py" cleanup --config "$CFG_FILE"` でこのrunの設定だけを削除する。別runの設定は削除しない。
