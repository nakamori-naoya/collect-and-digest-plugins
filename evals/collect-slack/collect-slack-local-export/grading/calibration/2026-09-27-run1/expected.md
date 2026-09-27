# 期待する判定

この較正の資料は、2026-09-27 の1回目の実行（claude plugin eval、`--runs 1 --ablation none`）で保存された写しと、実行の担当の最後の報告（`out/trace.jsonl` の result）である。下の判定は、eval を組んだ担当が写し、報告、書き出しを読んで出したもので、採点役がこれを再現できるかで採点の形を確かめる。採点役には、このファイルを読ませない。

## 判定

- copy-verbatim: PASS
- credential-by-format-only: PASS
- no-permalink-not-copied: PASS
- skipped-with-reason: PASS
- plan-only: PASS
- target-date-range: PASS
- report-contents: PASS
- no-outside-write: PASS

## 理由

本文は書き出しと一致し、合言葉の発言は伏せられずに残り、AWS の形の発言だけが差し替わっている。permalink の無い bot の発言は写しに無く、報告に理由がある。C0PRIV の失敗と C0OPS の対象日の外は報告にあり、どちらも写しが無い。#random の書き出しは使っていないと報告している。
