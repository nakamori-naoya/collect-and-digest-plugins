> 共通の規約は /Users/naoya-nakamoriq/Documents/Github/harness-pluginsv2/AGENTS.md にある。ここには、この repository だけの規則を置く。

# AGENTS.md

このrepositoryは収集とdigestのmarketplaceである。marketplaceへ公開するインストール対象はpackage `collect-and-digest`（`./plugins/collect-and-digest`）だけにし、公開入口は `skills/` 直下の `collect-notes` / `collect-slack` / `collect-sessions` / `digest` / `make-session-digest` の5つとする。内部skillは置かない。各入口は自身の `SKILL.md`、`references/`、`scripts/`、`assets/` と、package共有code `lib/collection_store.py` だけで完結する。複数工程を持つ入口（`digest` / `make-session-digest`）は隣接 `playbook.yml` の宣言順を実行順の正式な定義にし、同じagentが辿る。

設定は1層の設定file（repositoryの `.harness-plugins/<入口>.config.yml`、`collect-sessions` だけ利用者の `${XDG_CONFIG_HOME:-~/.config}/harness-plugins/collect-sessions.config.yml`）を、各入口の `scripts/config.py check|read`（stdin不要、pathはtoolが固定、stdoutにJSON 1文書、失敗はexit 2と `reason`）が読んでschemaを検査する。schemaの正式な定義は各入口のtoolの `validate_config` で、`config.py` はそれを共有する。同梱既定へのfallbackと層の探索を置かない。`assets/<入口>.config.example.yml` は記入例であり既定値ではない。
