---
name: digest
description: 収集物（議事録・Slack・セッション索引など日付directoryの下に並ぶfront matter付きMarkdown）を期間で選び、`period-digest` 型の資料を1本作る。「日次まとめを作って」「今週の議事録をダイジェストにして」「月次まとめを作って」と言われたとき、また「どんなdigestがあるか」「いま素材が何件あるか」と聞かれたときに使う。収集と執筆そのものは扱わない。
---

# digest

溜まった収集物から、期間を区切って `period-digest` 型の資料を1本作る。議事録は「いつ何を話したか」の順に並んでいるが、読み手が要るのは「いま何が未決か」「何が決まったか」で並んだものである。**時間順から状態順への並べ替えが、この仕事の本体である。** 書くこと自体は `write-doc` の公開契約へ委ね、この入口が決めるのは「どの素材から・どの期間で・どの型で・どこへ・何を追加で重視するか」だけである。

## 入力

- `user_input`: 「daily を作って」「今週のまとめ」「どんなdigestがあるか」のような依頼。
- `references`: 任意。追加で従う資料の絶対path配列。手順の最初に読み、`write-doc` の `references` へそのまま渡す。プロジェクト固有の規約や文脈は、対象repositoryのAGENTS.md / CLAUDE.mdとこの入力で渡される。
- 設定file: `<repository root>/.harness-plugins/digest.config.yml`。素材の置き場 `sources`、出力先 `output`、digestの定義 `digests`（`name`、`period`、`type: period-digest`、`prompt`）を持つ。記入例は [`assets/digest.config.example.yml`](assets/digest.config.example.yml) にある。

同じagentが、同じdirectoryの [`playbook.yml`](playbook.yml) を読み、その `steps` の宣言順を実行順の正式な定義にする。

## 判断基準

- **資料を作る依頼か、定義と素材数を知りたい依頼か。** 「どんなdigestがあるか」「素材は何件か」なら手順1と2だけを行い、設定の `digests` と `sources` 、`material.py list` の件数（選択と除外）を示して終える。除外件数が素材件数より多いときは置き場か期間の設定を疑うと添える。
- **依頼はどのdigest定義に当たるか。** 依頼を `digests[].name` と `period` へ照合し、`digest_name` と基準時刻（省略時は今日）を確定する。依頼の語（「今週」「日次」など）から一つに絞れるなら、それを仮説として採り報告に明記する。どの定義にも当たらず絞れないなら、資料を書いても無意味になるので候補を示して止まる。
- **素材は0件か。** 0件なら書かずに終わり、「その期間に素材が無い」と報告する。「置き場が無い」と「その期間に素材が無い」は別であり、`skipped` を見て設定ミスが疑われればそれを添える（[素材の扱い](references/sourcing.md)）。
- **型は固定か。** `document_type` は `period-digest` 固定で渡す。他の型が要るなら `write-doc` を直接呼ぶ（[作れる型](references/types.md)）。
- **出典に戻れるか。** 素材の `url` を持ち回り、資料の各項目から元の発言へ戻れるようにする。文字起こし（`parts: true`）は既定で読まず、本文の記述が疑わしいときだけ開く。参加者は素材本文から読み取って埋め、読み取れなければ `participants_note` に理由を書く。

## 手順

1. **設定を読み、依頼を照合する（`interpret-request`）。** `python3 scripts/config.py read --repo <repository配下のpath>` で `<git root>/.harness-plugins/digest.config.yml` を読む。設定が無いか形が違えば（`type` が `period-digest` 以外も含む）、終了code `2` と診断が返るので止まる。`values.digests` と `values.sources` を依頼と照合し、対象の `digest_name` と `reference_time` を確定する。以降の `material.py` / `doc-meta.py` の `--config` には `read` が返した `config` の絶対pathを渡す。
2. **素材を選ぶ（`material`）。** `python3 scripts/material.py list --config <設定file> --digest <digest_name> [--ref <YYYY-MM-DD>]` を実行する（明示期間は `--from` / `--to` の両方）。出力は `from` / `to` / `label` / `count` / `items` / `skipped` / `type` / `output` / `prompt` を持つ標準出力のJSON、終了codeは `0` = 選んだ、`2` = 設定不備・型違反・期間不正（診断は標準出力のJSON `error`）。`2` なら止まる。`count` が0なら手順3以降へ進まず報告する。
3. **静的情報の骨格を作る（`meta`）。** `python3 scripts/doc-meta.py skeleton --config <設定file> --digest <digest_name> --from <from> --to <to> [--label <label>] [--materials <items JSON>]` を実行する。出力は参加者だけが空の骨格JSON、終了codeは `0` = 作った、`2` = 不備。参加者を埋め、資料の末尾へ人が読む表と同じ内容のJSON（Markdownは `<!-- doc-meta:begin ... doc-meta:end -->` のHTML comment）として載せるよう素材に含める。
4. **資料化を委譲する（`document`）。** 公開Skill `write-doc:write-doc` へ次を直接渡す。`material` は選択した各素材を `{kind: file, path: <絶対path>}` にし、静的情報の骨格を `{kind: text, content: <本文>}` として加え、追加promptが空でなければ同じく `kind: text` の要素として加えたobject配列。`document_type` は `period-digest`。`output_directory` は `output.dir` をrepository root基準で解決した絶対path、`name` はdigest名と期間から決めた `.md` file名。同じpathの既存資料を更新すると利用者が明示した場合だけ、この2つに代えて `update_target` を渡す。入力の `references` があればそのまま `references` に渡す。返ったobjectの `status` が `completed` なら `path` を資料の絶対pathとして報告し、`failed` なら `reason` を報告して止まる。
5. **報告する。** 期間と `label`、素材の件数と拾わなかった件数、書いたfileの絶対path、付いたラベル（後で `doc-meta.py group` で束ねる手がかり）。

## 停止条件

止まるのは次の場合である。診断または `reason` を報告し、資料が書けたことにしない。

- `config.py` が `2` を返した。
- 依頼がどの `digests[].name` にも当たらず、依頼の語からも一つに絞れない。候補を示して止まる（必須入力の欠落）。
- 素材が0件。書かずに「その期間に素材が無い」と報告して終わる。
- `write-doc` が `failed` を返した。

次は止まらず、仮説を明示して進む。

- 依頼の語からdigest定義が一つに絞れる、基準時刻の指定が無い。その定義と今日を仮説として採り、報告に明記する。
- 参加者を素材本文から読み取れない。`participants_note` に理由を書いて進む。
- 除外件数が素材件数より多い。置き場か期間の設定ミスの可能性を報告に添えて進む。

## 出力

`period-digest` 型のMarkdown資料1本の絶対pathと、手順5の報告。照会の依頼では定義と素材数の報告だけを返す。
