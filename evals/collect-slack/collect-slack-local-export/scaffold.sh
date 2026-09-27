#!/usr/bin/env bash
# 手元の書き出しと設定を、共通の準備で作業場所へ置く。
set -euo pipefail
CASE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec bash "$CASE_DIR/../../scaffold.sh" "$CASE_DIR"
