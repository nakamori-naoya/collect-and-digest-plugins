---
name: make-digest
description: 複数directoryの収集物から日次・週次・月次の資料を1本作る。期間で素材を選び、設定の追加promptを渡し、型を3種（期間ダイジェスト／決定ログ／論点台帳）に絞って資料化させる。「日次まとめを作って」「今週の議事録をダイジェストにして」「月次の決定ログを作って」と言われたときに使う。
---

# make-digest

**溜まった収集物から、期間を区切って資料を1本作る。**

議事録は「いつ何を話したか」の順に並んでいる。読み手が要るのは「いま何が未決か」「何が決まったか」で並んだものである。**時間順から状態順への並べ替えが、このスキルの本体である。**

## 0. プラグイン root を決める

<!-- BEGIN shared:skill-entry/root-block -->
```bash
BUNDLE_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
if [ -d "${BUNDLE_ROOT}/playbooks/collection/digest" ]; then
  PLUGIN_ROOT="${BUNDLE_ROOT}/playbooks/collection/digest"
else
  PLUGIN_ROOT="${BUNDLE_ROOT}"
fi
```

`PLUGIN_ROOT`は配布物rootの絶対パスである。単一skill pluginではこの`SKILL.md`があるdirectory、複数skill pluginでは`skills/<skill>/`の2つ上に当たる。Claude Codeでは`${CLAUDE_PLUGIN_ROOT}`が自動展開される。
<!-- END shared:skill-entry/root-block -->

## 1. 工程を解決して、書かれた順に実行する

<!-- BEGIN shared:skill-entry/config-load -->
```bash
CFG_FILE=$(bash "${PLUGIN_ROOT}/scripts/prepare.sh" "$(pwd)") || exit 2
```

**このコマンドは説明例ではない。必ず実行する。** 解決済みYAMLが空なら先へ進まない。設定ファイルを直接読んで代用しない。

本文中の `${...}` は解決済みYAMLのプロパティである。使用時に `yq -er` で読み、欠落または `null` なら停止する。
<!-- END shared:skill-entry/config-load -->

`${.instructions.execution.directive}` に従い、`${.playbook.sources}`、`${.playbook.digests}`、`${.deps}` を工程へ渡す。

**各工程を呼ぶときは `--scope=${.resolution.scope_root}` を必ず渡す。**この段取りを通るときだけ効く設定がそこにある。渡さなければ効かない。入れ子の段取りへは、受け取ったものをそのまま渡す（自分の名前で作り直さない）。

**exit 2 で止まったら先へ進まない。** 何が起きたかは `scripts/resolve.sh` の冒頭に書いてある。

## 2. 素材の扱いを守る

素材が0件なら、**書かずに終わる**。「その期間に素材が無い」と報告する。
**「置き場が無い」と「その期間に素材が無い」は別のことである。** 詳しくは[素材の扱い](references/sourcing.md)。

## 3. 作れる型は3種だけ

`period-digest` だけ。**これ以外は作れない。**
使い分けと、型を固定して渡す理由は[作れる型](references/types.md)。

制限は設定の解決時に機械が検査する。**この文章を読み飛ばしても、設定が外れていれば止まる。**

## 4. write-docへ資料化を委譲する

書くのはこのskillではない。`document`工程で契約ID `write-doc/write-doc` の公開playbookへ、次の入力objectを直接渡す。入力YAML、解決済みYAML、依存先の`prepare.sh`、結果受取用ファイルは作らない。

- `material`: 選択した各素材を`{kind: file, path: <絶対path>}`にし、静的情報の骨格を`{kind: text, content: <本文>}`として加えたobject配列。追加promptが空でなければ、同じく`kind: text`の要素として加える
- `document_type`: 素材選択が返した`period-digest`
- `output_directory`: `output.dir`をrepository root基準で解決した絶対path
- `name`: digest名と期間から決めた`.md`ファイル名
- `references`: 追加で従わせる既存資料が明示された場合だけ、その読み取り可能な絶対path配列

`material`へpath文字列だけを渡さない。追加promptは素材であり、`references`用の一時ファイルへ書き出さない。保存先を既定値で補わない。新規作成では`output_directory`と`name`を必ず組にする。同じpathの既存資料を更新すると利用者が明示した場合だけ、この2つに代えて`update_target`へ確認済みの絶対pathを渡す。両方式を同時に渡さない。

公開playbookが直接返した`status`を確認する。`completed`なら`path`を資料の絶対pathとして報告する。`failed`なら`reason`を報告して停止し、資料が書けたことにしない。返却値に`path`と`reason`の両方がある場合や、契約にない値がある場合も停止する。

## 5. 報告する

- 期間と `label`
- 素材の件数と、拾わなかった件数
- 書いたファイルの**絶対パス**
- 付いたラベル（後で束ねるときの手がかりになる）

後から束ねる方法と工程上書きの形式は[README](../../README.md)を参照する。`steps` を書いた場合は丸ごと差し替わる。

設定生成で返却された絶対pathを実行記録へ残す。別shellでは記録した絶対pathを `CFG_FILE` へ明示代入して読む。処理が成功・停止・失敗した最後に `python3 "${PLUGIN_ROOT}/scripts/run-config.py" cleanup --config "$CFG_FILE"` でこのrunの設定だけを削除する。別runの設定は削除しない。
