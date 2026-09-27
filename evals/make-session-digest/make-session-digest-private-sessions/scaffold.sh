#!/usr/bin/env bash
# 偽のセッションと write-doc のファイルを共通の準備で置き、collect-sessions の利用者設定を
# 作業場所の中の xdg/ に書く。セッションの置き場も索引の置き場も作業場所の中を指し、
# 利用者の本物のセッションの置き場を読ませない。
set -euo pipefail
CASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
bash "$CASE_DIR/../../scaffold.sh" "$CASE_DIR" with-write-doc
WORK=$(pwd)
# 索引は非公開の置き場なので、git に入らないようにする。
printf 'state/\n' >> .gitignore
# 写したセッションは今の時刻を持つので、書き終わったセッションとして読まれるよう、最後の行の日に戻す。
find sessions -name '*.jsonl' -exec touch -t 202609202300 {} +
mkdir -p xdg/harness-plugins
cat > xdg/harness-plugins/collect-sessions.config.yml <<YAML
version: 1
state_dir: $WORK/state/session-collect
timezone: Asia/Tokyo
sources:
  claude_code:
    enabled: true
    root: $WORK/sessions/claude
  codex:
    enabled: false
    root: $WORK/sessions/codex
collection:
  include_subagents: false
  max_scan_files: 100
  max_source_bytes: 1048576
  stable_read_retries: 3
  quiescent_after_minutes: 30
YAML
