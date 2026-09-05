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
trap 'rm -f "$CFG_FILE"' EXIT
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

`period-digest` / `decision-log` / `open-questions` のいずれか。**これ以外は作れない。**
使い分けと、型を固定して渡す理由は[作れる型](references/types.md)。

制限は設定の解決時に機械が検査する。**この文章を読み飛ばしても、設定が外れていれば止まる。**

## 4. 追加promptを渡す

素材選択が返す`prompt`を、型や文章規律を置き換えない追加指示として資料作成工程へそのまま渡す。空文字なら追加指示なしとして扱う。設定にない指示を補わない。

## 5. 報告する

- 期間と `label`
- 素材の件数と、拾わなかった件数
- 書いたファイルの**絶対パス**
- 付いたラベル（後で束ねるときの手がかりになる）

後から束ねる方法と工程上書きの形式は[README](../../README.md)を参照する。`steps` を書いた場合は丸ごと差し替わる。
