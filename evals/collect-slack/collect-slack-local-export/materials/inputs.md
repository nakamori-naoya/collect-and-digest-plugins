# 実行の担当に渡した入力

実行の担当には、作業場所の直下に次のものを置いて渡した。

`slack-export/` は、Slack の MCP の代わりに置いた書き出しである。collect-slack の計画の操作の応答に当たるものを、操作の id の名前で置いた。`resolve-authenticated-user.json` は本人の解決、`search-direct-mentions-all.json` と `search-authored-threads-all.json` は二つの検索の結果、`read-matched-threads/<チャンネルID>-<thread_ts>.json` は、スレッドごとの読み取りの応答である。`unplanned/` には、計画に無い操作（#random のチャンネルの読み取り）の応答が、書き出しに混ざっている。

設定は `.harness-plugins/collect-slack.config.yml` で、保存先は `out/slack`、対象は直接メンションと本人の発言のスレッド、チャンネルは all、認証情報の形の差し替えは有効である。対象日は 2026-09-20（Asia/Tokyo）と指示した。
