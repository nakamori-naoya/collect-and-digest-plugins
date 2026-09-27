#!/usr/bin/env bash
# ケースが共有する準備。空の作業場所を、設定を置ける git の作業ツリーにし、ケースの材料を置く。
# 資料を書く入口のケースには、write-doc の最新のファイルを写す。write-doc は隔離環境に入らないので、
# 兄弟 checkout から写し、無ければ写しで代用せずに止まる。
#
#   bash scaffold.sh <ケースのディレクトリ> [with-write-doc]
set -euo pipefail

[ $# -ge 1 ] || { echo "使い方: bash scaffold.sh <ケースのディレクトリ> [with-write-doc]" >&2; exit 2; }
CASE_DIR=$(cd "$1" && pwd)
EVALS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY=$(cd "$EVALS_DIR/.." && pwd)
WORKSPACE=$(cd "$(dirname "$REPOSITORY")" && pwd)

git init -q .
# 収集の入口は、保存先が git に入らないことを確かめてから書く。
printf 'out/\n' > .gitignore
mkdir -p .harness-plugins out
cp -R "$CASE_DIR/materials/." .
rm -f inputs.md
if [ -d "$CASE_DIR/config" ]; then
  cp "$CASE_DIR"/config/*.yml .harness-plugins/
fi
if [ "${2:-}" = with-write-doc ]; then
  WRITE_DOC="$WORKSPACE/write-doc-plugins/plugins/write-doc/skills/write-doc"
  [ -f "$WRITE_DOC/SKILL.md" ] || { echo "兄弟 checkout の skill が無い: $WRITE_DOC" >&2; exit 2; }
  mkdir -p harness
  cp -R "$WRITE_DOC" harness/write-doc
fi
