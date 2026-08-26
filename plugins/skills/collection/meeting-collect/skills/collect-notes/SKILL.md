---
name: collect-notes
description: Notion / Google Docs の議事録のうち、設定timezone上の対象日（既定は今日）に属するものを1箇所へ集めて保存する。要約も抽出もしない。「議事録を集めて」「collect-notes」「今日のミーティングノートを取り込んで」と言われたときに使う。
---

# collect-notes

このentryは配布形式を中立化する薄い入口である。次を実行してplugin rootを検証し、root直下の正本`SKILL.md`を全文読んで、その手順に従う。

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
bash "${PLUGIN_ROOT}/scripts/prepare.sh" --root-only >/dev/null || exit 2
cat "${PLUGIN_ROOT}/SKILL.md"
```
