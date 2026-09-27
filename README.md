# Collect and Digest

会議、Slack、agent sessionを収集し、期間digestを作るClaude Code/Codex両対応marketplaceである。公開するインストール対象はpackage `collect-and-digest`（`./plugins/collect-and-digest`）1件で、公開入口は自己完結skill 5つ（`collect-notes` / `collect-slack` / `collect-sessions` / `digest` / `make-session-digest`）である。

## こんなときに使う

**会議、Slack、AIセッションに散らばった活動を、日付と出典を保ったまま集め、後から追える資料へまとめたいときに使う。** 収集と要約を別工程にするため、原文の取得範囲とdigestの編集判断を混同しない。

- 今日の会議記録をNotionとGoogle Docsから一箇所へ集めたい
- 自分が関わったSlack threadをpermalink付きで保存したい
- Claude CodeとCodexの活動を、原文を複製せず非公開索引にしたい
- 複数の収集directoryから日次、週次、月次のdigestを作りたい
- 決定事項だけ、または未決の論点だけを期間横断で追いたい

## 公開入口を選ぶ

次の入口から依頼します。各入口は `SKILL.md`、`references/`、`scripts/`、`assets/` だけで完結し、内部skillを持ちません。

| 欲しい結果 | 公開入口 | 設定file |
|---|---|---|
| Notion / Google Docsの議事録を対象日で集める | `collect-notes` | `<repo>/.harness-plugins/collect-notes.config.yml` |
| Slackの発言を対象日で集める | `collect-slack` | `<repo>/.harness-plugins/collect-slack.config.yml` |
| Claude Code / Codexのsessionを非公開索引にする | `collect-sessions` | `${XDG_CONFIG_HOME:-~/.config}/harness-plugins/collect-sessions.config.yml` |
| 複数の収集物から期間資料を作る（定義と素材数の照会も） | `digest` | `<repo>/.harness-plugins/digest.config.yml` |
| session索引から日次の短い記録を作る | `make-session-digest` | 無し（保存先は依頼の `output_directory` で受け取る） |

設定fileは必須で、同梱の既定値へのfallbackは無い。各入口の `assets/<入口>.config.example.yml` を写して書く。設定が無いか形が違えば、各入口の `scripts/config.py read` が終了code 2と診断を返し、入口は止まる。収集の入口は上流を読むだけで、書き込みはしない。

collectorは要約しない。`digest`は収集元を変更しない。この分離により、収集漏れの確認と要約内容のレビューを別々に行える。

## 利用例

```text
今日の会議記録と、自分が関わったSlack threadを収集して。
```

```text
今週の収集物から、決定事項に絞った週次digestを1本作って。
```

```text
今日活動したClaude CodeとCodexのsessionを索引化し、日次記録を作って。
```

## インストール

インストールするのは`collect-and-digest@collect-and-digest`です。外部の工程を実行するため、`write-doc@write-doc`も必要です。下のコマンドには、それらも含めています。

内部のスキルは同梱されています。個別にインストールせず、公開入口から利用してください。

### Codex

利用するCodexと同じ設定環境で実行してください。

```bash
codex plugin marketplace add nakamori-naoya/write-doc-plugins
codex plugin add write-doc@write-doc
codex plugin marketplace add nakamori-naoya/collect-and-digest-plugins
codex plugin add collect-and-digest@collect-and-digest
codex plugin list
```

一覧で導入先を確認し、新しい会話で利用してください。

### Claude Code

次は自分の全プロジェクトで使う例です。このプロジェクトのチームで共有する場合は`project`、このプロジェクトで自分だけが使う場合は`local`に変更し、利用先のディレクトリで実行してください。

```bash
CLAUDE_PLUGIN_SCOPE=user
claude plugin marketplace add nakamori-naoya/write-doc-plugins --scope "$CLAUDE_PLUGIN_SCOPE"
claude plugin install write-doc@write-doc --scope "$CLAUDE_PLUGIN_SCOPE"
claude plugin marketplace add nakamori-naoya/collect-and-digest-plugins --scope "$CLAUDE_PLUGIN_SCOPE"
claude plugin install collect-and-digest@collect-and-digest --scope "$CLAUDE_PLUGIN_SCOPE"
claude plugin list
```

一覧で導入を確認し、Claude Codeを再起動してください。すでに導入しているパッケージは、次の更新手順を使ってください。

## 更新する

GitHubから登録したmarketplaceを更新し、その公開パッケージを更新します。新規インストールと同じCodexの設定環境、Claude Codeの適用範囲を使ってください。

### Codex

```bash
codex plugin marketplace upgrade collect-and-digest
codex plugin add collect-and-digest@collect-and-digest
codex plugin list
```

更新後は新しい会話で確認してください。ローカルのパスからmarketplaceを登録した場合は、Git版の更新コマンドではなく、その登録先のソースを更新してから追加し直します。

### Claude Code

```bash
# インストール時に合わせてuser / project / localを選ぶ
CLAUDE_PLUGIN_SCOPE=user
claude plugin marketplace update collect-and-digest
claude plugin update collect-and-digest@collect-and-digest --scope "$CLAUDE_PLUGIN_SCOPE"
claude plugin list
```

更新後はClaude Codeを再起動してください。外部の依存パッケージも使っている場合は、それぞれのREADMEの更新手順を実行してください。

marketplaceの取得と、インストール済みパッケージの更新は分けて確認します。同じバージョンとして公開された変更は、更新コマンドだけでは反映されない場合があります。「最新」と表示された場合は公開バージョンを確認し、キャッシュ内のファイルを直接編集しないでください。

コマンドは2026-09-06時点のCLIヘルプと、[Codexのmarketplace管理](https://developers.openai.com/plugins/build/plugins)、[Claude Codeの更新仕様](https://code.claude.com/docs/en/plugins-reference#plugin-update)を確認しています。

## インストール済みである必要があるplugin

このrepository外の依存だけを記載する。

- `write-doc@write-doc`

別repositoryへの依存は `digest` と `make-session-digest` の `playbook.yml` の `requires` に `{plugin, marketplace}` で宣言し、`playbook:` の工程として呼ぶ。相手の内部機能名へ依存せず、versionは固定しない。

## 検証

```bash
bash scripts/validate.sh
```

入口が判断の要を外さないかは、`evals/` の下のケースで確かめる。Slack、Notion、Google Docs には eval の中で触れないので、ケースは手元に置いた材料（Slack の書き出し、集めた議事録と Slack の写し、作業場所の中の偽のセッション）だけで動く。collect-slack は写しを原文のまま、戻れるものだけ作るか、digest は時間順の素材を期間の終わりの状態へ並べ直すか、make-session-digest は日次記録を共有されるものとして書くかを見る。collect-notes は上流の MCP が要り、手元の材料では collect-slack と同じ判断しか確かめられないので、ケースを置いていない。

実行は repository の root で、ケースごとに次を動かす。`--scaffold` はケースの `scaffold.sh` を自分の権限で動かすので、この repository のケースにだけ使う。write-doc の skill は隔離環境に入らないので、兄弟 checkout `../write-doc-plugins/` から作業場所へ写す。

```bash
claude plugin eval . --case <ケース> --runs 1 --ablation none --keep-temp \
  --scaffold --allow-tools Write Edit Bash --max-cost-usd 5 --no-publish
```

出来は、別の Claude が条件ごとに3回判定し、重み付きの点数にする。採点の道具は harness-tools の `tools/grade-eval.sh` で、ケースと作業場所（`kept temp:` に出る一時ディレクトリ）を絶対パスで渡す。共通の条件は `evals/criteria/`、ケースに固有の条件は `evals/<入口>/<ケース>/grading/criteria.md`、採点役を確かめる資料と期待する判定は同じケースの `grading/calibration/` にある。較正の資料の最後の報告は、`out/trace.jsonl` の result の行に置いてある。

## 業務知識

- [収集とダイジェスト作成の業務知識と振る舞い](docs/2026-09-02-収集とダイジェスト作成-業務知識と振る舞い.md)

## 保守tool

保守用tool（release / test-hardening / validate-plugin-repository）の参照元は兄弟checkoutの `../harness-tools/` であり、このrepositoryは複製を持たない。`scripts/validate.sh` は `../harness-tools/tools/` の実在を確認してから呼び、無ければ止まる。CIの `validate.yml` も `harness-tools` を兄弟checkoutして `harness-tools/ci/validate.sh` を実行する。呼び方は `../harness-tools/README.md` にある。
