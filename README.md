# Collect and Digest

会議、Slack、agent sessionを収集し、期間digestを作るClaude Code/Codex両対応marketplaceである。

## こんなときに使う

**会議、Slack、AIセッションに散らばった活動を、日付と出典を保ったまま集め、後から追える資料へまとめたいときに使う。** 収集と要約を別工程にするため、原文の取得範囲とdigestの編集判断を混同しない。

- 今日の会議記録をNotionとGoogle Docsから一箇所へ集めたい
- 自分が関わったSlack threadをpermalink付きで保存したい
- Claude CodeとCodexの活動を、原文を複製せず非公開索引にしたい
- 複数の収集directoryから日次、週次、月次のdigestを作りたい
- 決定事項だけ、または未決の論点だけを期間横断で追いたい

## どの機能を使うか

| 欲しい結果 | 選ぶ機能 |
|---|---|
| 対象日の会議原文を集める | `meeting-collect` |
| 自分が関わったSlack threadを集める | `slack-collect` |
| Claude Code / Codex sessionの非公開索引を作る | `session-collect` |
| session索引から日次の短い記録を作る | `session-digest` |
| 複数の収集物から期間資料を作る | `digest` |

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

### Codex

Codexのpluginコマンドには`--scope`がない。通常の手順はuser単位でmarketplaceとpluginを登録する。

```bash
codex plugin marketplace add nakamori-naoya/collect-and-digest-plugins
codex plugin add collect-and-digest@collect-and-digest
```

このrepositoryだけに分離したい場合は、repository専用の`CODEX_HOME`を作り、インストール時と利用時に同じ値を指定する。

```bash
mkdir -p .codex-home
export CODEX_HOME="$PWD/.codex-home"

codex plugin marketplace add nakamori-naoya/collect-and-digest-plugins
codex plugin add collect-and-digest@collect-and-digest
codex
```

`CODEX_HOME`には認証、設定、ログ、session、plugin metadataも保存されるため、このdirectoryはGit管理しない。

### Claude Code

Claude Codeは次のscopeを選べる。

| scope | 対象 |
|---|---|
| `user` | user全体。省略時の既定値 |
| `project` | このrepositoryで有効にする設定をGitでチーム共有する |
| `local` | このrepositoryで有効にするが、Git共有せず自分だけで使う |

repository設定としてインストールする場合は`project`を指定する。`CLAUDE_PLUGIN_SCOPE`を`user`または`local`へ変えれば、同じ手順でscopeを切り替えられる。

```bash
CLAUDE_PLUGIN_SCOPE=project

claude plugin marketplace add nakamori-naoya/collect-and-digest-plugins --scope "$CLAUDE_PLUGIN_SCOPE"
claude plugin install collect-and-digest@collect-and-digest --scope "$CLAUDE_PLUGIN_SCOPE"
```

利用者がインストールするのはこのpackageだけである。`meeting-collect`、`session-collect`、`slack-collect`、`digest`、`session-digest`は選択できる内包機能であり、個別のインストール対象ではない。

## インストール済みである必要があるplugin

このrepository外の依存だけを記載する。

- `write-doc@write-doc`

別repositoryへの依存は公開playbook packageの`plugin@marketplace`だけを宣言し、内部機能名へ依存しない。versionは固定せず、開発用map、同じrepository、runtimeのinstall cacheの順に候補を調べ、解決したmanifestのidentityと必要なskillを検査する。

## 設定の上書きと優先順位

設定を持つpluginは、優先順位が最も高い1ファイルだけを選ぶ。複数層をマージしないため、上書きするYAMLには同梱設定と同じ必須項目をすべて含める。必須項目の不足、未知のキー、許可されていない値があれば実行を停止する。

skillの静的設定は、上から順に優先する。

1. scope: `<scope>/<plugin-name>.config.yml`。呼び出し元がscopeを渡した実行だけで使う
2. local: `<repo>/.harness-plugins/<plugin-name>.local.yml`。端末固有で、通常はcommitしない
3. repository: `<repo>/.harness-plugins/<plugin-name>.config.yml`
4. personal: `$XDG_CONFIG_HOME/harness-plugins/<plugin-name>.config.yml`（未設定時は `~/.config/harness-plugins/<plugin-name>.config.yml`）
5. bundled defaults: plugin同梱の既定設定

playbookの静的設定は、scope、repository、personal、同梱 `playbook.yml` の順で優先する。playbookにはlocal層がない。入口playbook自身は通常のrepository設定を使い、下段のpluginへscopeを渡す。単体呼び出しではscopeを読まない。

skillでは、同梱設定の `prompt_parameters` に宣言されたpathだけ、依頼で明示された値を `--override=<path>=<value>` として最終上書きできる。宣言されていないpathを任意に上書きすることはできない。

たとえば入口は `<repo>/.harness-plugins/digest.config.yml`、その入口から呼ぶ `write-doc` だけの設定は `<repo>/.harness-plugins/scopes/digest/write-doc.config.yml` に置く。

## 検証

```bash
bash scripts/validate.sh
```

## 業務知識

- [収集とダイジェスト作成の業務知識と振る舞い](docs/2026-09-02-収集とダイジェスト作成-業務知識と振る舞い.md)

## 実行契約の検証と配布

`python3 scripts/doctor.py --repository . --repo <対象repository>` はCLI構文、公開skillと設定・依存の解決を読み取り専用で診断する。設定解決を含めない検査は `--distribution-only` を明示する。

`bash scripts/validate.sh` は機能・不正入力・配布の検証を行い、GitHub Actionsの `validate (ubuntu-latest)` / `validate (macos-latest)` でも実行する。[意味的評価シナリオ](evals/scenarios.json)は `scripts/evaluate-skills.py` で実モデルと別のjudgeモデルへ渡し、モデルID・設定・入力・応答・判定根拠を記録する。モデル評価は構造検証と別に実施し、未実行を成功として扱わない。

version更新は `python3 scripts/release.py --plugin <公開plugin名> --version <semver> --notes <変更内容> --breaking <互換性への影響> --migration <移行方法> --checks <codex/claudeの検証結果JSON>` で計画を確認し、`--apply` で両runtimeのmanifestとmarketplaceを更新する。検証結果には未検証も明示できる。配布・外部publishは別操作であり、このcommandでは行わない。

### 破壊的変更と移行

公開入口は同名SKILLの薄い別入口を廃止して一意にした。古い内部SKILL pathを直接参照している呼出元は公開manifestのskillsへ切り替える。設定の一時fileはshell終了では削除されず、返却された絶対pathを次の工程へ渡し、完了・停止時にrun-configのcleanupでそのrunだけを削除する。以前の一時fileや異なる実行identityを再利用せず、新しいrunを開始する。

収集は追記archiveであり、現行snapshotとの完全同期を保証しない。Slack編集は旧本文をversionsへ保持し、明示削除はtombstoneにする。取得結果に無いだけで保存物を削除しない。会議の日付変更・transcript省略でも旧fileを履歴として保持し、最新台帳pathと現行partsを参照する。保存directory全体を排他し、中断された本文・台帳の更新は次回check/write/appendでjournalから回復する。台帳の構文またはschema破損は自動スキップせず停止するため、旧データは退避して内容を確認してから移行する。
