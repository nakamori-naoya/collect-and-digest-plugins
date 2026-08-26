---
name: collect-slack
description: 設定timezone上の対象日（既定は今日）の Slack を集めて保存する。設定から生成されたMCP実行計画に従い、全チャンネルまたは明示した複数チャンネルから、直接メンション・グループメンション・本人発言・通常投稿を明示的に選んで取る。要約も抽出もしない。「Slack を集めて」「今日の Slack を取り込んで」と言われたときに使う。
---

# collect-slack

このentryは配布形式を中立化する薄い入口である。次を実行してplugin rootを検証し、root直下の正本`SKILL.md`を全文読んで、その手順に従う。

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-/absolute/path/to/this/plugin}"
bash "${PLUGIN_ROOT}/scripts/prepare.sh" --root-only >/dev/null || exit 2
cat "${PLUGIN_ROOT}/SKILL.md"
```
