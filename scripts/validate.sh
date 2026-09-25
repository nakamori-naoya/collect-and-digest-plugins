#!/usr/bin/env bash
# Scenario: collect-and-digest package が公開入口5つで自己完結し、各入口の決定論的toolが閉じた契約を守る
# 機械検査は宣言と実体の対応、隣接playbook.ymlの契約、設定fileのschema、material の入出力だけを判定する。
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
ENTRIES=(collect-notes collect-sessions collect-slack digest make-session-digest)

# ── 配置と identity ──────────────────────────────────────────────────────
for market in .claude-plugin/marketplace.json .agents/plugins/marketplace.json; do
  if jq -e '.name=="collect-and-digest" and (.plugins|length)==1 and .plugins[0].name=="collect-and-digest" and .plugins[0].version=="6.1.1"
            and ((.plugins[0].source=="./plugins/collect-and-digest") or (.plugins[0].source=={"source":"local","path":"./plugins/collect-and-digest"}))' "$ROOT/$market" >/dev/null; then
    pass "$market identityとsource"
  else
    fail "$market identityとsource"
  fi
done
claude_identity=$(jq -c '{name,version,skills,harness:.metadata.harness}' "$PACKAGE/.claude-plugin/plugin.json")
codex_identity=$(jq -c '{name,version,skills,harness:.metadata.harness}' "$PACKAGE/.codex-plugin/plugin.json")
[ "$claude_identity" = "$codex_identity" ] && pass "両runtime manifestのidentity一致" || fail "両runtime manifestのidentity一致"
jq -e '.skills==["./skills/collect-notes","./skills/collect-sessions","./skills/collect-slack","./skills/digest","./skills/make-session-digest"]
       and .metadata.harness=={"marketplace":"collect-and-digest","contractVersion":1}' "$PACKAGE/.codex-plugin/plugin.json" >/dev/null \
  && pass "公開入口5つ、playbooks / internalPlugins / implements 無し" || fail "manifestの公開宣言"
manifest_dirs=$(find "$ROOT/plugins" -type d \( -name '.claude-plugin' -o -name '.codex-plugin' \) | sed "s#^$ROOT/##" | sort | tr '\n' ' ')
[ "$manifest_dirs" = "plugins/collect-and-digest/.claude-plugin plugins/collect-and-digest/.codex-plugin " ] \
  && pass "runtime manifest directoryはpackage rootの2つだけ" || fail "runtime manifest directoryが余分または欠落: $manifest_dirs"
skill_dirs=$(find "$ENTRY_DIR" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort | tr '\n' ' ')
[ "$skill_dirs" = "collect-notes collect-sessions collect-slack digest make-session-digest " ] && pass "skills/直下は公開入口5つだけ" || fail "skills/直下: $skill_dirs"
[ "$(find "$ROOT/plugins" -name SKILL.md -type f | wc -l | tr -d ' ')" -eq 5 ] && pass "SKILL.mdは公開入口の5本だけ（内部skillなし）" || fail "SKILL.mdの本数"
[ "$(find "$ROOT/plugins" -type l | wc -l | tr -d ' ')" -eq 0 ] && pass "配布物にsymlinkなし" || fail "配布物にsymlinkがある"
[ -f "$PACKAGE/lib/collection_store.py" ] && pass "package共有code lib/collection_store.py" || fail "lib/collection_store.py"

# ── 公開入口ごとの構造 ─────────────────────────────────────────────────
for entry in "${ENTRIES[@]}"; do
  dir="$ENTRY_DIR/$entry"
  name=$(awk 'NR==1 { if ($0 != "---") exit 2; next } $0=="---" { exit } { print }' "$dir/SKILL.md" | yq -r '.name')
  [ "$name" = "$entry" ] && pass "$entry: SKILL frontmatter name" || fail "$entry: SKILL frontmatter name = $name"
  if rg -n --fixed-strings -e '${.' -e '<!-- BEGIN shared:' -e 'CLAUDE_PLUGIN_ROOT' -e 'BUNDLE_ROOT' "$dir" --glob '!*.pyc' >/dev/null \
    || rg -n 'prepare\.sh|resolve\.sh|run-config\.py|state\.py|finalize\.sh|CFG_FILE' "$dir/SKILL.md" "$dir/references" >/dev/null; then
    fail "$entry: 禁止参照形または旧runtime呼び出しが残っている"
  else
    pass "$entry: 禁止参照形と旧runtime呼び出しが無い"
  fi
done
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
# 境界例: 対象日に0件（exit 4）、旧形の --out-dir / --cleanup 引数（argparseで拒否）、fileが生成されないこと。
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

  # 反例: 原文が無い、相対path。境界例: 旧形の引数は受け付けない。
  jq -c '.source_ref.path="'"$fixture/absent.jsonl"'"' "$fixture/day-index.jsonl" > "$fixture/absent-index.jsonl"
  if (cd "$fixture/non-git" && python3 "$script" --day-index "$fixture/absent-index.jsonl" --date 2026-09-02) >/dev/null 2>&1; then status=1; fi
  if (cd "$fixture" && python3 "$script" --day-index day-index.jsonl --date 2026-09-02) >/dev/null 2>&1; then status=1; fi
  if python3 "$script" --day-index "$fixture/day-index.jsonl" --date 2026-09-02 --out-dir "$fixture/old" >/dev/null 2>&1; then status=1; fi
  if python3 "$script" --cleanup --material-path "$fixture/x.json" --path "$fixture/y.md" --index "$fixture/day-index.jsonl" >/dev/null 2>&1; then status=1; fi
  [ ! -e "$fixture/old" ] || status=1

  # playbookに一時file配管が無い。
  yq -o=json -I=0 '.' "$ENTRY_DIR/make-session-digest/playbook.yml" | jq -e '([.steps[].id]|index("cleanup")|not) and ([.steps[]|.provides[]?]|index("material_path")|not) and ([.steps[]|.provides[]?]|index("material"))' >/dev/null || status=1
  return "$status"
}


validate_session_digest_material_fixture && pass "make-session-digest material.py の標準出力material・0件・provisional・旧引数拒否" || fail "make-session-digest material.py"

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

# ── repositoryの回帰検査（harness-tools）: CI workflowのSHA固定、公開入口の一意性、doctorの読み取り専用性 ──
python3 "$TOOLS/test-hardening.py" --repository "$ROOT" && pass "test-hardening --repository" || fail "test-hardening --repository"

# ── 消費側の契約lint（harness-tools）: 外部依存の内部名を消費側の文書・script・設定へ書いていない ──
# 検出語は兄弟checkoutの実配布物（provider package root）から作る。兄弟が無ければ緑にせず失敗させる。
lint_consumer_contract() {
  local map="$TMP_ROOT/lint-dev-map.json" status=0 runtime
  local grill="$ROOT/../grill-plugins/plugins/grill" write_doc="$ROOT/../write-doc-plugins/plugins/write-doc" awp="$ROOT/../agent-work-policy-plugins/plugins/agent-work-policy"
  for provider in "$grill" "$write_doc" "$awp"; do
    [ -d "$provider" ] || { echo "[error] 依存先の配布物checkoutが無い: $provider" >&2; return 1; }
  done
  jq -n --arg g "$(cd "$grill" && pwd -P)" --arg w "$(cd "$write_doc" && pwd -P)" --arg a "$(cd "$awp" && pwd -P)" \
    '{schema:1,dependencies:{"grill/grill":$g,"write-doc/write-doc":$w,"agent-work-policy/agent-work-policy":$a}}' > "$map" || return 1
  for runtime in claude codex; do
    HARNESS_PLUGIN_DEV_ROOTS="$map" python3 "$TOOLS/lint-consumer-contract.py" --repo "$ROOT" --runtime "$runtime" || status=1
  done
  return "$status"
}
lint_consumer_contract && pass "消費側契約lint（両runtime。依存先の内部名を書いていない）" || fail "消費側契約lint"

if [ "$failed" -eq 0 ]; then echo 'Validation: passed'; else echo 'Validation: failed'; fi
[ "$failed" -eq 0 ]
