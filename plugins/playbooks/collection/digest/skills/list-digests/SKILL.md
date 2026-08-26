---
name: list-digests
description: この playbook がどんな工程を、どの順で回すかと、いま素材が何件あるかを出す。「どんな digest があるか」「何を素材にしているか」「工程はどうなっているか」を聞かれたときに使う。
---

# list-digests（定義を見る）

## 0. プラグイン root を決める

<!-- BEGIN shared:skill-entry/root-block -->
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
```

`PLUGIN_ROOT`は配布物rootの絶対パスである。単一skill pluginではこの`SKILL.md`があるdirectory、複数skill pluginでは`skills/<skill>/`の2つ上に当たる。Claude Codeでは`${CLAUDE_PLUGIN_ROOT}`が自動展開される。
<!-- END shared:skill-entry/root-block -->

## 1. 工程と依存を出す

<!-- BEGIN shared:skill-entry/config-load -->
```bash
CFG_FILE=$(bash "${PLUGIN_ROOT}/scripts/prepare.sh" "$(pwd)") || exit 2
trap 'rm -f "$CFG_FILE"' EXIT
```

**このコマンドは説明例ではない。必ず実行する。** 解決済みYAMLが空なら先へ進まない。設定ファイルを直接読んで代用しない。

本文中の `${...}` は解決済みYAMLのプロパティである。使用時に `yq -er` で読み、欠落または `null` なら停止する。
<!-- END shared:skill-entry/config-load -->

`${.instructions.execution.directive}` に従い、`${.playbook.sources}`、`${.playbook.digests}`、`${.deps}` を表示する。

**各工程を呼ぶときは `--scope=${.resolution.scope_root}` を必ず渡す。**この段取りを通るときだけ効く設定がそこにある。渡さなければ効かない。入れ子の段取りへは、受け取ったものをそのまま渡す（自分の名前で作り直さない）。

stderr へ、**工程の順番**と**依存の解決先**が出る。**設定が壊れていればここで exit 2 になる**ので、その内容をそのまま見せる。

## 2. いまの素材数を出す

素材を数えるのは、素材選びの工程の仕事である。**この playbook はその工程を呼ぶだけで、数え方は知らない。**

`${.playbook.steps}` から `provides` に `items` を持つ工程を選び、その `script` を実行して素材数を得る。

**除外件数が素材件数より多いときは、置き場か期間の設定を疑う。**
