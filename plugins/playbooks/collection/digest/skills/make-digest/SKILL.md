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

`period-digest` / `decision-log` / `open-questions` のいずれか。**これ以外は作れない。**
使い分けと、型を固定して渡す理由は[作れる型](references/types.md)。

制限は設定の解決時に機械が検査する。**この文章を読み飛ばしても、設定が外れていれば止まる。**

## 4. write-docへ資料化を委譲する

書くのはこのskillではない。依存先`write-doc`の公開playbookへ、**契約の入力・出力だけで**渡す。**委譲は2段で行い、実行設定の解決（prepare）を走らせるのは1回だけで、それはこちらの仕事である。** 相手の工程、内部の段取り、保存の仕組みには触れない。

### 4-1. 契約入力のYAMLを書く

repository外の実行専用subdirectoryへ0600で置く。書けるキーはこれだけである。

```yaml
contract: write-doc/write-doc
version: 1
document_type: <素材選択が返した資料の型>
material:
  - <素材選択が返した素材を書き出したファイルの絶対path>
  - <静的情報の骨格を書き出したファイルの絶対path>
output_format: <output.format の値>
output_directory: <output.dir を展開した絶対path>
name: <digests[].name と期間から決めたファイル名>
references:
  - <追加promptを書き出したファイルの絶対path>
output_to: <結果を受け取るYAMLの絶対path>
```

- `material` は絶対pathの配列である。素材と骨格を別ファイルにして並べてよい。
- 型は`document_type`として**固定して渡す**。素材選択が返した値以外を書かない。この型は実行時に決まるので、`playbook.yml`の`steps[].input`ではなくこの契約入力で渡す。
- **ここに無いキーは書かない。** 未知のキーがある入力は受け付けられない。
- 素材選択が返す`prompt`は、型や文章の規律を置き換えない追加指示である。空文字なら`references`ごと省く。設定にない指示を補わない。`references`へ書けるのはこのplaybookが持つ資料だけで、依存先が持つ資料は指さない。
- **新規に作るときだけ** `name` を書く。保存先は`output.dir`が決めているので、あわせて `output_directory` も書く（`output_directory` だけを書くことはできない）。同じpathの既存資料を更新すると決めたときは、その2つを書かず、確認済みの絶対pathを `update_target` に書く。`name` と `update_target` は排他で、両方を書いた入力も、どちらも書かない入力も受け付けられない。

### 4-2. 第1段 — こちらがprepareし、解決済みYAMLのpathを得る

```bash
WRITE_DOC_CFG=$(bash "${.deps.write-doc.root}/scripts/prepare.sh" "$(pwd)" \
  --input=<4-1で書いたYAMLの絶対path> \
  --scope=${.resolution.scope_root} \
  --bindings=${.resolution.bindings_lock}) || exit 2
```

受け取ったscopeと束縛は作り直さず、そのまま渡す。exit 2 なら先へ進まない。**この段は省けない。** 省くと相手は単独起動と見なして自分でprepareし、契約入力もscopeも束縛も届かない。

### 4-3. 第2段 — 入口SKILL.mdへ解決済みYAMLを渡して実行し、結果を受け取る

`${.deps.write-doc.entry}` が入口SKILL.mdの絶対pathである。それを読み、**4-2で得た`$WRITE_DOC_CFG`を渡して**書かれた手順どおりに実行する。相手はprepareをやり直さず、渡された解決済みYAMLをそのまま使う。手順を要約したり、skill名やそれ以外のpathから別の入口を組み立てたりしない。

完了したら`output_to`のYAMLを読む。`status: completed` なら `path` が保存された資料1本の絶対pathで、それを報告する。`status: failed` なら `reason` を報告して停止し、資料が書けたことにしない。

4-2で作った解決済みYAMLはこちらの持ち物であり、相手は消さない。こちらも、後始末のために相手の配布物にあるscriptを実行しない。

## 5. 報告する

- 期間と `label`
- 素材の件数と、拾わなかった件数
- 書いたファイルの**絶対パス**
- 付いたラベル（後で束ねるときの手がかりになる）

後から束ねる方法と工程上書きの形式は[README](../../README.md)を参照する。`steps` を書いた場合は丸ごと差し替わる。

設定生成で返却された絶対pathを実行記録へ残す。別shellでは記録した絶対pathを `CFG_FILE` へ明示代入して読む。処理が成功・停止・失敗した最後に `python3 "${PLUGIN_ROOT}/scripts/run-config.py" cleanup --config "$CFG_FILE"` でこのrunの設定だけを削除する。別runの設定は削除しない。
