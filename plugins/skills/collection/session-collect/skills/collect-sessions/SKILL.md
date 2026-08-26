---
name: collect-sessions
description: Claude Code / Codex のローカルセッションを、原文を複製せず対象日に活動したセッションの非公開索引として収集する。「セッションを集めて」「今日のCodex作業を記録して」「collect-sessions」と依頼されたときに使う。
---

# collect-sessions

このentryは配布形式を中立化する薄い入口である。次を実行してplugin rootを検証し、root直下の正本`SKILL.md`を全文読んで、その手順に従う。

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
bash "${PLUGIN_ROOT}/scripts/prepare.sh" --root-only >/dev/null || exit 2
cat "${PLUGIN_ROOT}/SKILL.md"
```
