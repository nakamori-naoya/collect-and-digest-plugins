---
name: make-digest
description: 複数directoryの収集物から日次・週次・月次の期間ダイジェストを1本作る。期間で素材を選び、設定の追加promptを渡して資料化させる。「日次まとめを作って」「今週の議事録をダイジェストにして」「月次まとめを作って」と言われたときに使う。
---

# make-digest

**溜まった収集物から、期間を区切って資料を1本作る。**

議事録は「いつ何を話したか」の順に並んでいる。読み手が要るのは「いま何が未決か」「何が決まったか」で並んだものである。**時間順から状態順への並べ替えが、このスキルの本体である。**

## 1. 実行契約を受け取り、書かれた順に進める

このSKILLを実行する同じagentが、2階層上の`../../playbook.yml`と本文から参照する資料を全文読み、利用者の入力と明示された資料を保持した一つの文脈で最後まで判断する。本文の`${.playbook...}`と`${.instructions...}`は、agentが`../../playbook.yml`から読んだ値を指し、外部runtimeから注入される値ではない。認知工程を別skillへrelayせず、`skill:`工程の責務と参照資料をこのagent自身が適用する。決定論的な`script:`工程は公開playbook directoryの実在するtoolへ明示した入力pathを渡し、stdoutまたは指定した出力pathから結果を受け取る。`playbook:`工程だけは依存先の公開Skillを名前で呼び、その公開入力と公開結果だけを使う。設定生成、scope、依存先rootの探索、一時設定の寿命管理は行わない。必要な入力、宣言値、tool結果、公開Skill結果が無ければ推測せず停止する。

同じagentが`../../playbook.yml`の`instructions.execution.directive`、`sources`、`digests`、`requires`を直接読む。外部依存は`requires`の`{plugin, marketplace}`と利用可能な公開Skill名を照合し、別runtimeの依存解決objectを前提にしない。素材選択toolへ期間とsource directoryを明示し、その直接結果を使う。失敗結果を受けたら先へ進まない。

`steps`配列が工程順序の正本である。最初の`interpret-request`は`agent_work: invoking_agent`として、このSKILLを実行している同じagentが利用者の依頼を`digests`の宣言へ照合し、`digest_name`と`reference_time`を確定する。その2値を明示してから`material`の決定論的toolを呼び、配列順を自由に入れ替えない。

## 2. 素材の扱いを守る

素材が0件なら、**書かずに終わる**。「その期間に素材が無い」と報告する。
**「置き場が無い」と「その期間に素材が無い」は別のことである。** 詳しくは[素材の扱い](references/sourcing.md)。

## 3. 作れる型は1種だけ

`period-digest` だけ。**これ以外は作れない。**
使い分けと、型を固定して渡す理由は[作れる型](references/types.md)。

型の制限は`playbook.yml`の機械可読な`digests`宣言と素材選択toolの出力schemaを照合する。説明文の語句では判定しない。

## 4. write-docへ資料化を委譲する

書くのはこのskillではない。`document`工程で公開Skill `write-doc:write-doc`へ、次の入力objectを直接渡す。中間ファイルや依存先の実行状態は作らない。

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
