---
name: collect-sessions
description: Claude Code / Codexのローカルセッションを、原文を複製せず対象日に活動したセッションの非公開索引として収集する。「セッションを集めて」「今日のCodex作業を記録して」「collect-sessions」と依頼されたときに使う。
---

# collect-sessions

対象日に活動したClaude Code / Codexのセッションを見つけ、元のfileへの参照と決定的なメタデータだけを非公開の `state_dir` へ索引として残す。要約は別の仕事である。

## 原文は写さない

索引に入れるのは参照とメタデータだけで、プロンプト、応答、tool の入出力、system prompt は写さない。セッションには secret や他人の情報が混ざりうるので、写しを増やせばそのまま漏れる先が増えるからである。成功の報告にも本文、native ID、pathを出さない。形式と不透明化の決まりは[セッション形式と収集契約](references/workflow.md)にある。

## 止まるか、1件だけ飛ばすか

壊れたものは止まり、形が違うだけのものは1件だけ飛ばす。有効にした source の root が無い、JSONLの途中が本当にparseできない、上限を超えた、索引が壊れた、保存先が安全でない、のどれかなら止まる。一方、対象の形でないfile（sessionIdを持たないWorkflowのjournalなど）や、turnやtimestampをまだ持たない空のセッションは、理由を記録して飛ばし、`counts.unrecognized` に数える。末尾が書きかけのセッションは `provisional` として載せる。

## 手順

1. **対象日を決める。** 指定が無ければ設定の `timezone` の当日にし、報告に書く。対象日は、その日のtimestampを持つイベントがあるかで決め、開始日では決めない。
2. **設定を読み、走査する。** `python3 scripts/config.py read` で `${XDG_CONFIG_HOME:-~/.config}/harness-plugins/collect-sessions.config.yml` を読む。セッションの置き場はmachineごとに違うので、この設定はrepositoryではなく利用者ごとに置く。設定が無いか形が違えば、終了code `2` と診断が返るので止まる。記入例は [`assets/collect-sessions.config.example.yml`](assets/collect-sessions.config.example.yml) にある。続けて `python3 scripts/session.py scan --config <readが返したconfig> --date <YYYY-MM-DD>` を実行し、`2` なら止まる。事前の確認だけなら `--dry-run` を付ける。
3. **報告する。** 対象日、`counts`（discovered / written / updated / unchanged / skipped / unrecognized / provisional）、日次索引、`provisional` の有無を報告する。0件でも `counts` を示す。
