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

**委譲は2段で行う。実行設定の解決（prepare）を走らせるのは1回だけで、それはこちらの仕事である。** 相手の工程、内部の段取り、保存の仕組みには一切触れない。

### 3-1. 契約入力のYAMLを書く

repository外の実行専用subdirectoryへ0600で置く。書けるキーはこれだけである。

```yaml
contract: write-doc/write-doc
version: 1
document_type: <${.playbook.contract.document_type} の値>
material:
  - <material.py が返した material_path>
output_format: <${.playbook.output.format} の値>
output_directory: <${.playbook.output.dir} を展開した絶対path>
name: <${.playbook.contract.output_name} の <target_date> を対象日へ置換した値>
references:
  - <references/output.md の絶対path>
  - <references/privacy.md の絶対path>
output_to: <結果を受け取るYAMLの絶対path>
```

- `material` は絶対pathの配列である。1本でも配列で書く。
- **新規に作るときだけ** `name` を書く。保存先は`${.playbook.output.dir}`が決めているので、あわせて `output_directory` も書く（`output_directory` だけを書くことはできない）。
- **既存資料を同じpathへ更新すると決めたときは**、`output_directory` と `name` を書かず、確認済みの絶対pathを `update_target` に書く。`name` と `update_target` は排他で、両方を書いた入力も、どちらも書かない入力も受け付けられない。
- `references` はこのplaybookが持つ2本だけを渡す。依存先が持つ資料を指さない。
- **ここに無いキーは書かない。** 未知のキーがある入力は受け付けられない。

### 3-2. 第1段 — こちらがprepareし、解決済みYAMLのpathを得る

```bash
WRITE_DOC_CFG=$(bash "${.deps.write-doc.root}/scripts/prepare.sh" "$(pwd)" \
  --input=<3-1で書いたYAMLの絶対path> \
  --scope=${.resolution.scope_root} \
  --bindings=${.resolution.bindings_lock}) || exit 2
```

受け取ったscopeと束縛は作り直さず、そのまま渡す。exit 2 なら先へ進まない。**この段は省けない。** 省くと相手は単独起動と見なして自分でprepareし、契約入力もscopeも束縛も届かない。

### 3-3. 第2段 — 入口SKILL.mdへ解決済みYAMLを渡して実行し、結果を受け取る

`${.deps.write-doc.entry}` が入口SKILL.mdの絶対pathである。それを読み、**3-2で得た`$WRITE_DOC_CFG`を渡して**書かれた手順どおりに実行する。相手はprepareをやり直さず、渡された解決済みYAMLをそのまま使う。手順を要約したり、skill名やそれ以外のpathから別の入口を組み立てたりしない。

完了したら`output_to`のYAMLを読む。`status: completed` なら `path` が保存された資料1本の絶対pathで、これをdocument工程の`path`として次へ渡す。`status: failed` なら `reason` を報告して停止し、資料が書けたことにしない。

3-2で作った解決済みYAMLはこちらの持ち物であり、相手は消さない。こちらも、後始末のために相手の配布物にあるscriptを実行しない。

### 同じpathに既存資料があるとき

成果物は`<output.dir>/<対象日>.md`。同名の既存資料があるときは、**依頼する前に**こちらで既存を読み、front matterの`input_hash`を比較する。同じなら何も依頼せず終了する。異なり、かつ利用者からその既存pathの更新が明示されているときだけ、3-1で`update_target`にその絶対pathを書く。明示が無ければ資料化を依頼しない。独自の保存scriptやforceオプションは持たない。0件では空の成果物を書かない。

cleanupはdocumentが返した`path`とcollectが返した`index`、今回の`material_path`が揃った後にだけ最終stepとして実行する。3つの明示pathを`material.py --cleanup`へ渡す。

```bash
python3 "${PLUGIN_ROOT}/scripts/material.py" --cleanup \
  --material-path <material_path> --path <path> --index <index>
```

出力JSON全体を`cleanup_report`として扱う。cleanupはmaterial file 1件だけをunlinkし、0700の実行専用directoryは残す。

設定生成で返却された絶対pathを実行記録へ残す。別shellでは記録した絶対pathを `CFG_FILE` へ明示代入して読む。処理が成功・停止・失敗した最後に `python3 "${PLUGIN_ROOT}/scripts/run-config.py" cleanup --config "$CFG_FILE"` でこのrunの設定だけを削除する。別runの設定は削除しない。
