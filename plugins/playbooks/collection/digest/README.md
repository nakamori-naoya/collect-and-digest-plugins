# digest

**収集された複数の場所と実行定義を指定したら、日次・週次・月次の資料を1本作る。** 出力先はこのプラグインの設定が持つ。

書くこと自体は `compose-doc` に任せる。**digest が決めるのは「どの素材から・どの期間で・どの型で・どこへ・何を追加で重視するか」だけ。**

```
notes/  slack/  ─→ digest ─→ compose-doc ─→ docs/2026-W33-weekly.html
（収集された場所）    ↑                          （digest の設定が決める出力先）
                 期間・型・追加prompt
```

## なぜ自分で書かないか

自分で書くと、HTML の雛形もマーカーの見た目も文章規律も、`doc-compose` と**二重に持つ**ことになる。片方を直しても、もう片方が古いまま残る。

**依存は片方向。** `doc-compose` は digest の存在を知らないし、digest が無くても単体で使える。

## 使える型は3種だけ

| 型 | 何を並べるか |
|---|---|
| `period-digest` | 期間 × 全ソース横断の1枚。決定／未決／アクション／動きの4区画 |
| `decision-log` | 決まったことだけを1件1エントリ |
| `open-questions` | 未決の相談事項を、状態と滞留期間つきで |

**これ以外は作れない。** 制限しないと「何でも作れる汎用ディスパッチャ」に戻る。収集物からチュートリアルや API リファレンスを作ることに意味は無い。**他の型が要るなら `compose-doc` を直接呼ぶ。**

制限は素材を選ぶ工程（`scripts/material.py`）が機械で検査する。**スキルの文章だけに乗せると、飛ばしても何の信号も出ない。**

```
$ material.py list --digest weekly
[error] digest 'weekly' の type が使えない: tutorial
        digest から使えるのは period-digest decision-log open-questions のみ。
        他の型が要るなら compose-doc を直接呼ぶこと。
```

## 使う

```
/make-digest daily        設定の daily を作る
/make-digest weekly       設定の weekly を作る（月曜〜日曜）
/make-digest month        設定の month を作る
/list-digests             定義と、いまの素材数
```

## 設定

`<repo>/.harness-plugins/digest.config.yml`。同梱`playbook.yml`を丸ごと複製し、完全な設定として編集する。工程だけの部分設定は使えない。

```yaml
version: 2
name: digest
description: 収集物から資料を1本作る
instructions:
  execution: {directive: stepsを上から順に実行し、needsを前工程のprovidesから受け取る}
requires:
  - {plugin: write-doc, marketplace: write-doc}

output:                 # 全体の既定
  dir: docs
  format: html          # html / markdown
  theme: dark           # dark / light / auto

sources:                # 全digestで共有。相対pathはrepository root基準
  - dir: notes
  - dir: slack
labels: []

digests:
  - name: daily
    period: daily
    type: period-digest
    prompt: "今日から引き継ぐ未完了事項を先に出す"

  - name: weekly
    period: weekly      # daily / weekly / monthly
    type: period-digest # 必須。3種のいずれか。既定へは倒さない
    prompt: "今週の決定と来週の行動を対にする"

  - name: month
    period: monthly
    type: period-digest
    prompt: "月をまたいで残る論点を明示する"
    output:             # digest ごとに上書きできる
      format: markdown

steps:                     # 同梱playbook.ymlのsteps全体を持つ
  - {id: material, script: scripts/material.py, purpose: 置き場と期間から素材を選ぶ, provides: [items, skipped, period, type, output, prompt]}
  - {id: meta, script: scripts/doc-meta.py, purpose: 静的情報の骨格を作る, needs: [items, period], provides: [meta]}
  - {id: document, playbook: write-doc, purpose: 素材と型から資料を書く, needs: [items, period, type, output, prompt, meta], provides: [path]}
```

`requires`は`plugin`と`marketplace`のidentityだけを持ち、versionは固定しない。解決時に選んだmanifestのidentityと、工程が指すskillやplaybookの存在を検査する。

| キー | 意味 |
|---|---|
| `sources[].dir` | 全digestが読む置き場。複数指定でき、相対パスはリポジトリ root 基準 |
| `period` | `daily` / `weekly`（月曜始まり）/ `monthly` |
| `prompt` | 資料作成工程へそのまま渡す追加指示。追加指示がなければ空文字 |
| `include_parts` | `part:` を持つファイル（文字起こし）を含めるか（既定 false） |
| `type` | **必須。** 上の3種のいずれか |
| `output.*` | 出力先・形式・テーマ。`compose-doc` へ上書きとして渡す |

## 資料の末尾に載る静的情報

**資料自身が、機械で読める形の情報を持つ。** 別に台帳を作ると資料と台帳がずれるので、正本は資料の中に置く。

```
| 期間     | 2026-08-10 〜 2026-08-16（2026-W33） |
| 作成     | 2026-08-14T12:00:00+09:00           |
| 種別     | weekly / period-digest              |
| 参加者   | …                                    |
| 素材     | 4件                                  |
| ラベル   | team:hidane kind:weekly digest:weekly type:period-digest period:2026-W33 source:notes source:slack |
```

人が読む表の下に、同じ内容が JSON で埋まっている（HTML は `<script type="application/json">`、Markdown は HTML コメント）。**後から読み直せる。**

```bash
doc-meta.py index docs/            # 情報を持つ資料を JSONL で一覧
doc-meta.py group docs/ --by team  # ラベルのキーで束ねる
```

### ラベル

**任意の数を、自由に付けられる。形は検査しない。** 形を強制すると「使える語彙」を機械が決めることになる。

| 出どころ | 例 |
|---|---|
| 設定（全体・digest ごと） | `team:hidane` `kind:weekly` |
| 自動 | `digest:weekly` `type:period-digest` `period:2026-W33` `source:notes` |
| 内容から書き手が足す | `topic:採用` |

`key:value` の形にしておくと `group --by key` で束ねられる。素のラベルはそのラベル名で束ねられる。

```yaml
labels: [org:yoikagari]       # 全体に付く
digests:
  - name: weekly
    labels: [team:hidane, kind:weekly]
    prompt: "担当者が不明なアクションを分けて出す"
```

**参加者を空のまま残さない。** 読み取れなければ理由を書く。空配列は「参加者ゼロ」と読まれる。

## 素材の条件

置き場の下がこうなっていればよい。**誰が作ったかは問わない。**

```
<dir>/<YYYY-MM-DD>/*.md      先頭に --- で囲んだ front matter がある
```

| front matter のキー | 使い道 |
|---|---|
| `source` / `source_id` | どこから来たか |
| `url` | **元へ戻るリンク。資料の出典に使う** |
| `title`（無ければ `label` / `bucket` / ファイル名） | 見出し |
| `occurred_at` | いつの出来事か |
| `part` | あれば既定で除外（文字起こしなど） |
| `parts` | あれば「文字起こしを持つ」印 |

**front matter が無いファイルは黙って捨てず、`skipped` に理由つきで出す。**

## 定期実行

```yaml
# .harness-plugins/cadence.config.yml
jobs:
  - name: weekly-digest
    run: /make-digest weekly
    every: 24h
```

## しないこと

- **収集しない。** 集めるのは収集プラグイン
- **書かない。** 書くのは `compose-doc`
- **チケットを作らない。** アクションは「未処理として一覧に出る」ところまで
- **素材0件のときに空の資料を作らない**
- **中身を機械で検査しない。** 型の allowlist 以外は見ない
