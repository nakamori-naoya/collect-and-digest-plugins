# 実行の担当に渡した入力

実行の担当には、作業場所の直下に次のものを置いて渡した。

`notes/` と `slack/` は、collect-notes と collect-slack がすでに集めた収集物の代わりに置いたもので、日付のディレクトリの下に front matter 付きの Markdown が並ぶ。2026-09-10 の議事録は期間の外、`notes/2026-09-16/メモ.md` は front matter の無いファイルである。

設定は `.harness-plugins/digest.config.yml` で、素材の置き場は `notes` と `slack`、保存先は `out/digest`、digest の定義は weekly の一つだけである。write-doc の skill は環境に入っていないので、その最新のファイルを `harness/write-doc/` に写した。

依頼は、2026-09-18 を含む週の weekly の digest を `out/digest/weekly-2026-W38.md` に作ることである。
