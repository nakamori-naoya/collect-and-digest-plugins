---
name: digest
description: 収集物を期間と型で選び、digest playbookを実行して資料を1本作る
---

# Digest playbook

この入口は、収集済みの素材から日次・週次・月次の digest を作る playbook です。

`playbook.yml` を実行定義として読み、設定された `sources`、期間、資料の型、出力先を検査してから、定義された順序で工程を進めてください。個別工程の `list-digests` と `make-digest` はこの playbook 内部の手順として扱い、単独の公開入口として扱わないでください。

利用方法と設定項目は同じ directory の `README.md` を参照してください。
