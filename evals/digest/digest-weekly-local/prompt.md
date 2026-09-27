---
plugins: ["../../../plugins/collect-and-digest"]
description: 手元に置いた一週間分の議事録と Slack の写しから、digest で weekly の period-digest を作らせる。週の途中で決定が変わり、月曜の未決が木曜に閉じ、担当の決まらない作業と推測の発言、期間の外の素材と front matter の無い素材を混ぜてある。
tags: [digest, local-materials]
max_turns: 150
timeout_seconds: 3000
allowed_tools: [Read, Glob, Grep, Skill, TodoWrite, Write, Edit, Bash]
---

今週（2026-09-18 を含む週）の weekly の digest を作ってください。この作業場所が repository で、設定は `.harness-plugins/digest.config.yml` にあります。資料は `out/digest/weekly-2026-W38.md` に保存してください。

## ほかの package のファイル

この環境には write-doc の skill が入っていません。代わりに、その最新のファイルを `harness/write-doc/` に写してあります。skill が write-doc へ資料化を渡すよう求めたら、`harness/write-doc/SKILL.md` を読み、その入力の形と手順に従って、あなた自身が書いてください。

## 報告

最後に、日本語で、skill が求める報告を書いてください。
