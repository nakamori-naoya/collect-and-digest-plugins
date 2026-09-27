#!/usr/bin/env bash
# Scenario: collect-and-digest package の各入口の決定論的toolが閉じた契約を守る
# 配置と manifest は harness-tools の validate-plugin-repository.py が判定する。ここでは隣接playbook.ymlの契約、設定fileのschema、material の入出力だけを判定する。
# 収集内容の妥当性、要約の品質、SKILL本文の判断基準の十分性は意味評価として残す。
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# 保守toolの参照元は兄弟checkoutの harness-tools。無ければ止まる（fixtureで代用しない）。
TOOLS="$ROOT/../harness-tools/tools"
[ -d "$TOOLS" ] || { echo "[error] 兄弟 checkout harness-tools が無い: $TOOLS" >&2; exit 2; }
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/collect-and-digest-validation.XXXXXX") || exit 2
export TMPDIR="$TMP_ROOT"
export PYTHONDONTWRITEBYTECODE=1
trap 'rm -rf "$TMP_ROOT"' EXIT
failed=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; failed=1; }

PACKAGE="$ROOT/plugins/collect-and-digest"
ENTRY_DIR="$PACKAGE/skills"

# ── 配置と manifest（harness-tools） ─────────────────────────────────────
python3 "$TOOLS/validate-plugin-repository.py" "$ROOT" && pass "package 構造（harness-tools）" || fail "package 構造（harness-tools）"
[ -f "$PACKAGE/lib/collection_store.py" ] && pass "package共有code lib/collection_store.py" || fail "lib/collection_store.py"

# ── 公開入口ごとの構造 ─────────────────────────────────────────────────
# 型は入口ごとに固定: digest は period-digest、make-session-digest は agent-session-digest（型の基準資料は write-doc の template）。
for entry in digest make-session-digest; do
  dir="$ENTRY_DIR/$entry"
  pb=$(yq -o=json -I=0 '.' "$dir/playbook.yml")
  case "$entry" in digest) doc_type=period-digest ;; make-session-digest) doc_type=agent-session-digest ;; esac
  jq -e --arg n "$entry" --arg t "$doc_type" '.version==2 and .name==$n and .requires==[{"plugin":"write-doc","marketplace":"write-doc"}]
      and ((.steps|map(.id)|unique|length)==(.steps|length))
      and all(.steps[]; ([has("agent_work"),has("script"),has("skill"),has("playbook")]|map(select(.))|length)==1)
      and all(.steps[]|select(has("playbook")); .playbook=="write-doc")
      and ((.steps[]|select(.id=="document")).input.document_type==$t) and ((.contract.document_type // $t)==$t)
      and (.. | objects | has("digests") | not)' <<<"$pb" >/dev/null \
    && pass "$entry: playbook.yml identity・外部requires・工程種別・型固定" || fail "$entry: playbook.yml"
  scripts_ok=1
  while IFS= read -r script; do [ -f "$dir/$script" ] || scripts_ok=0; done < <(jq -r '.steps[]|select(has("script")).script' <<<"$pb")
  [ "$scripts_ok" -eq 1 ] && pass "$entry: steps.script は入口内の実在file" || fail "$entry: steps.script の参照先"
done
jq -e '.steps[0].skill=="collect-sessions"' <<<"$(yq -o=json -I=0 '.' "$ENTRY_DIR/make-session-digest/playbook.yml")" >/dev/null \
  && [ -f "$ENTRY_DIR/collect-sessions/SKILL.md" ] && pass "make-session-digest: steps.skill は同packageの公開入口 collect-sessions" || fail "make-session-digest: steps.skill"
for entry in collect-notes collect-sessions collect-slack; do
  [ ! -f "$ENTRY_DIR/$entry/playbook.yml" ] && pass "$entry: 単一工程の入口はplaybook.ymlを持たない" || fail "$entry: playbook.yml"
done
for entry in collect-notes collect-sessions collect-slack digest; do
  [ -f "$ENTRY_DIR/$entry/assets/$entry.config.example.yml" ] && pass "$entry: 設定の記入例がある" || fail "$entry: 設定の記入例"
done

# ── 構文 ────────────────────────────────────────────────────────────────
while IFS= read -r script; do bash -n "$script" || failed=1; done < <(find "$ROOT/scripts" "$ROOT/tests" -type f -name '*.sh' | sort)
while IFS= read -r script; do python3 -m py_compile "$script" || failed=1; done < <(find "$PACKAGE" -type f -name '*.py' | sort)

# ── 決定論的toolの契約 ────────────────────────────────────────────────
python3 -m unittest discover -s "$ROOT/tests" -p test_collection_integrity.py && pass "collection_store / 設定schema / 置き場解決の単体検査" || fail "tests/test_collection_integrity.py"

# make-session-digest material.py: 索引からmaterialを標準出力へ返す。fileは書かない。
# 基準資料: 索引のschema（REQUIRED_INDEX_KEYS）。入力: --day-index の絶対pathと --date。正規化: JSONL行ごとのparse。
# 合格述語: 対象日の完成済みroot sessionをrecordsにし、artifact.material / input_hash / target_date / session_count を返す。
# 診断: 標準出力の JSON error、exit 2 / 4。正例: 1 root session。反例: provisional、原文欠落、相対path。
# 境界例: 対象日に0件（exit 4）、fileが生成されないこと。
validate_session_digest_material_fixture() {
  local fixture="$TMP_ROOT/session-digest-material"
  local script="$ENTRY_DIR/make-session-digest/scripts/material.py"
  local status=0
  mkdir -p "$fixture/non-git"
  fixture=$(cd "$fixture" && pwd -P)

  printf '%s\n' '{"schema":1,"source":"fixture","source_id":"root","activity_dates":["2026-09-02"],"relation":"root","parent_source_id":null,"state":"quiescent","provisional":false,"source_ref":{"path":"'"$fixture/source.jsonl"'","fingerprint":"fixture"},"observed_at":"2026-09-02T00:00:00Z","collector":"fixture"}' > "$fixture/day-index.jsonl"
  printf '%s\n' '{}' > "$fixture/source.jsonl"
  (cd "$fixture/non-git" && python3 "$script" --day-index "$fixture/day-index.jsonl" --date 2026-09-02) > "$fixture/generated.json" || status=1
  jq -e '.decision=="written" and
    (.artifact|keys|sort)==["input_hash","material","session_count","target_date"] and
    (.artifact.material|type=="array" and length==1) and
    (.artifact.material[0]|keys|sort)==["collector","display","observed_at","parent_source_id","relation","source","source_fingerprint","source_id","source_path","target_date"] and
    .artifact.material[0].display==true and
    .artifact.target_date=="2026-09-02" and .artifact.session_count==1 and
    (.artifact.input_hash|test("^[0-9a-f]{64}$")) and
    .counts.items==1' "$fixture/generated.json" >/dev/null || status=1
  # fileを書かない: fixture配下に生成物が増えていない（non-gitは空のまま）。
  [ -z "$(find "$fixture/non-git" -mindepth 1)" ] || status=1
  [ -z "$(find "$fixture" -name 'session-material-*')" ] || status=1

  # 代表入力からwrite-doc v2のtyped materialへ、kind:textとして直接接続できる。
  jq -n --slurpfile generated "$fixture/generated.json" \
    --arg output_directory "$fixture/output" \
    '{material:[{kind:"text",content:($generated[0].artifact.material|tojson)}],
      document_type:"agent-session-digest",output_directory:$output_directory,
      name:($generated[0].artifact.target_date+".md")}
    | select((.material|length==1) and .material[0].kind=="text" and (.material[0].content|fromjson|length==1) and
        .document_type=="agent-session-digest" and (.output_directory|type=="string") and
        .name=="2026-09-02.md" and (has("update_target")|not))' >/dev/null || status=1

  # 対象日に0件なら exit 4 で止まり、空の最終資料も作らない。
  (cd "$fixture/non-git" && python3 "$script" --day-index "$fixture/day-index.jsonl" --date 2026-09-03) >/dev/null 2>&1
  [ "$?" -eq 4 ] || status=1

  # provisionalは完成済み素材ではないため、documentへ進まず止まる（exit 2）。
  jq -c '.provisional=true' "$fixture/day-index.jsonl" > "$fixture/provisional-index.jsonl"
  (cd "$fixture/non-git" && python3 "$script" --day-index "$fixture/provisional-index.jsonl" --date 2026-09-02) >/dev/null 2>&1
  [ "$?" -eq 2 ] || status=1

  # 反例: 原文が無い、相対path。
  jq -c '.source_ref.path="'"$fixture/absent.jsonl"'"' "$fixture/day-index.jsonl" > "$fixture/absent-index.jsonl"
  if (cd "$fixture/non-git" && python3 "$script" --day-index "$fixture/absent-index.jsonl" --date 2026-09-02) >/dev/null 2>&1; then status=1; fi
  if (cd "$fixture" && python3 "$script" --day-index day-index.jsonl --date 2026-09-02) >/dev/null 2>&1; then status=1; fi
  return "$status"
}


validate_session_digest_material_fixture && pass "make-session-digest material.py の標準出力material・0件・provisional" || fail "make-session-digest material.py"

# digest material.py: 設定fileの1層読み取り、期間、型固定、0件 / skipped の区別
validate_digest_material() {
  local repo="$TMP_ROOT/digest-repo" status=0 out
  mkdir -p "$repo/.harness-plugins" "$repo/notes/2026-09-15" "$repo/slack"
  cp "$ENTRY_DIR/digest/assets/digest.config.example.yml" "$repo/.harness-plugins/digest.config.yml"
  printf -- '---\nsource: notes\nsource_id: a\ntitle: t\noccurred_at: 2026-09-15T10:00:00+09:00\n---\nbody\n' > "$repo/notes/2026-09-15/a.md"
  printf 'no front matter\n' > "$repo/notes/2026-09-15/b.md"
  out=$(python3 "$ENTRY_DIR/digest/scripts/material.py" list --config "$repo/.harness-plugins/digest.config.yml" --digest daily --ref 2026-09-15) || status=1
  jq -e '.count==1 and (.skipped|map(select(.reason|test("front matter")))|length)==1 and .type=="period-digest" and .from=="2026-09-15" and .to=="2026-09-15"' <<<"$out" >/dev/null || status=1
  out=$(python3 "$ENTRY_DIR/digest/scripts/material.py" list --config "$repo/.harness-plugins/digest.config.yml" --digest daily --ref 2026-09-14) || status=1
  jq -e '.count==0' <<<"$out" >/dev/null || status=1
  if python3 "$ENTRY_DIR/digest/scripts/material.py" list --config "$repo/.harness-plugins/digest.config.yml" --digest absent --ref 2026-09-15 >/dev/null 2>&1; then status=1; fi
  if python3 "$ENTRY_DIR/digest/scripts/material.py" list --config "$repo/.harness-plugins/missing.yml" --digest daily >/dev/null 2>&1; then status=1; fi
  yq -i '.digests[0].type = "tutorial"' "$repo/.harness-plugins/digest.config.yml"
  if python3 "$ENTRY_DIR/digest/scripts/material.py" list --config "$repo/.harness-plugins/digest.config.yml" --digest daily >/dev/null 2>&1; then status=1; fi
  return "$status"
}
validate_digest_material && pass "digest material.py の設定読み取り・期間・型固定・skipped" || fail "digest material.py"

# ── repositoryの回帰検査（harness-tools）: CI workflowのSHA固定 ──
python3 "$TOOLS/test-hardening.py" --repository "$ROOT" && pass "test-hardening --repository" || fail "test-hardening --repository"

if [ "$failed" -eq 0 ]; then echo 'Validation: passed'; else echo 'Validation: failed'; fi
[ "$failed" -eq 0 ]
