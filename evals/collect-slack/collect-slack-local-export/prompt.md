---
plugins: ["../../../plugins/collect-and-digest"]
description: Slack の MCP の代わりに手元の書き出しを置き、2026-09-20 の Slack を collect-slack で集めさせる。permalink の無い発言、権限の無いスレッド、対象日の外の検索結果、計画に無い書き出し、意味で伏せたくなる発言と認証情報の形の発言を混ぜてある。
tags: [collect-slack, local-export]
max_turns: 120
timeout_seconds: 2400
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Write, Edit, Bash]
---

2026-09-20 の Slack を集めてください。この作業場所が repository で、設定は `.harness-plugins/collect-slack.config.yml` にあります。

## Slack の代わりの書き出し

この環境には Slack の MCP がつながっていません。代わりに、Slack の管理者が書き出したファイル一式を `slack-export/` に置きました。計画の操作の応答に当たるものは、操作の id の名前のファイルにしてあります。スレッドの読み取りの応答は `slack-export/read-matched-threads/<チャンネルID>-<thread_ts>.json` です。MCP の操作を実行する場面では、対応するファイルを読んで、その操作の応答として扱ってください。ワークスペースは example-team です。

## 報告

最後に、日本語で、skill が求める報告を書いてください。
