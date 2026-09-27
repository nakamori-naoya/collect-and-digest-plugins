# 期待する判定

この較正の資料は、2026-09-27 の1回目の実行（claude plugin eval、`--runs 1 --ablation none`）で保存された digest と、実行の担当の最後の報告（`out/trace.jsonl` の result）である。下の判定は、eval を組んだ担当が資料、報告、素材を読んで出したもので、採点役がこれを再現できるかで採点の形を確かめる。採点役には、このファイルを読ませない。

## 判定

- no-invented-facts: PASS
- speculation-marked: PASS
- source-links: PASS
- materials-accounted: PASS
- sections-kept: PASS
- changed-decision-latest: PASS
- closed-question-not-open: PASS

## 理由

リリース日は 10/1 だけが決定の表にあり、9/24 からの変更と理由が表の下の本文にある。手数料の問いは決まったことへ移り、p99 の改善の担当と、ログの保存年数は未決に残る。鈴木の「来週には直せる」は見込みとして書かれ、p99 の値には 1000rps とステージングの条件が付いている。
