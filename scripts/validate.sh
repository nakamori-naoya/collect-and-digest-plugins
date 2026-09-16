#!/usr/bin/env bash
# Scenario: collect-and-digest package が公開入口5つで自己完結し、各入口の決定論的toolが閉じた契約を守る
# 機械検査は宣言と実体の対応、隣接playbook.ymlの契約、設定fileのschema、material / cleanup の入出力だけを判定する。
# 収集内容の妥当性、要約の品質、SKILL本文の判断基準の十分性は意味評価として残す。
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
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
  if jq -e '.name=="collect-and-digest" and (.plugins|length)==1 and .plugins[0].name=="collect-and-digest" and .plugins[0].version=="4.0.0"
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
for entry in digest make-session-digest; do
  dir="$ENTRY_DIR/$entry"
  pb=$(yq -o=json -I=0 '.' "$dir/playbook.yml")
  jq -e --arg n "$entry" '.version==2 and .name==$n and .requires==[{"plugin":"write-doc","marketplace":"write-doc"}]
      and ((.steps|map(.id)|unique|length)==(.steps|length))
      and all(.steps[]; ([has("agent_work"),has("script"),has("skill"),has("playbook")]|map(select(.))|length)==1)
      and all(.steps[]|select(has("playbook")); .playbook=="write-doc")
      and ((.steps[]|select(.id=="document")).input.document_type=="period-digest")
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

validate_session_digest_material_fixture() {
  local fixture="$TMP_ROOT/session-digest-material"
  local script="$ENTRY_DIR/make-session-digest/scripts/material.py"
  local material="$fixture/private/session-material-fixture.json"
  local output="$fixture/final.md"
  local index="$fixture/index.jsonl"
  local status=0 out generated_material
  mkdir -p "$fixture/private" "$fixture/non-git"
  fixture=$(cd "$fixture" && pwd -P)
  material="$fixture/private/session-material-fixture.json"
  output="$fixture/final.md"
  index="$fixture/index.jsonl"
  chmod 700 "$fixture/private"
  printf '%s\n' 'final' > "$output"
  printf '%s\n' 'index' > "$index"

  make_material() { printf '%s\n' 'material' > "$1"; chmod 600 "$1"; }
  cleanup_ok() { python3 "$script" --cleanup --material-path "$1" --path "$output" --index "$index"; }
  cleanup_rejected() { if cleanup_ok "$1" >/dev/null 2>&1; then return 1; fi; [ -e "$1" ] || [ -L "$1" ]; }

  make_material "$material"
  out=$(cleanup_ok "$material") || status=1
  jq -e '.decision=="removed"' <<<"$out" >/dev/null || status=1
  [ ! -e "$material" ] || status=1
  out=$(cleanup_ok "$material") || status=1
  jq -e '.decision=="missing"' <<<"$out" >/dev/null || status=1

  make_material "$material"
  ln -s "$material" "$fixture/private/session-material-link.json"
  cleanup_rejected "$fixture/private/session-material-link.json" || status=1
  chmod 644 "$material"; cleanup_rejected "$material" || status=1; chmod 600 "$material"
  chmod 755 "$fixture/private"; cleanup_rejected "$material" || status=1; chmod 700 "$fixture/private"
  mkdir "$fixture/danger-root"; chmod 700 "$fixture/danger-root"
  make_material "$fixture/danger-root/session-material-dangerous.json"
  if TMPDIR="$fixture/danger-root" python3 "$script" --cleanup --material-path "$fixture/danger-root/session-material-dangerous.json" --path "$output" --index "$index" >/dev/null 2>&1; then status=1; fi
  [ -e "$fixture/danger-root/session-material-dangerous.json" ] || status=1
  if python3 "$script" --cleanup --material-path "$material" --path "$fixture/absent.md" --index "$index" >/dev/null 2>&1; then status=1; fi
  if python3 "$script" --cleanup --material-path "$material" --path "$material" --index "$index" >/dev/null 2>&1; then status=1; fi
  mkdir "$fixture/private/session-material-directory.json"
  cleanup_rejected "$fixture/private/session-material-directory.json" || status=1
  make_material "$fixture/private/not-session-material.json"
  cleanup_rejected "$fixture/private/not-session-material.json" || status=1

  printf '%s\n' '{"schema":1,"source":"fixture","source_id":"root","activity_dates":["2026-09-02"],"relation":"root","parent_source_id":null,"state":"quiescent","provisional":false,"source_ref":{"path":"'"$fixture/source.jsonl"'","fingerprint":"fixture"},"observed_at":"2026-09-02T00:00:00Z","collector":"fixture"}' > "$fixture/day-index.jsonl"
  printf '%s\n' '{}' > "$fixture/source.jsonl"
  (cd "$fixture/non-git" && python3 "$script" --day-index "$fixture/day-index.jsonl" --date 2026-09-02 --out-dir "$fixture/generated") > "$fixture/generated.json" || status=1
  jq -e '.decision=="written" and
    (.artifact|keys|sort)==["input_hash","material_path","session_count","target_date"] and
    (.artifact.material_path|startswith("'"$fixture"'")) and
    .artifact.target_date=="2026-09-02" and .artifact.session_count==1 and
    .counts.items==1' "$fixture/generated.json" >/dev/null || status=1
  generated_material=$(jq -r '.artifact.material_path' "$fixture/generated.json")
  [ -f "$generated_material" ] \
    && python3 -c 'import os, stat, sys; raise SystemExit(0 if stat.S_IMODE(os.stat(sys.argv[1]).st_mode) == 0o600 else 1)' "$generated_material" \
    || status=1

  # 代表入力からwrite-doc v2のtyped materialへ、唯一のproducer値を直接接続できる。
  mkdir -p "$fixture/output"
  jq -n --slurpfile generated "$fixture/generated.json" \
    --arg output_directory "$fixture/output" \
    '{material:[{kind:"file",path:$generated[0].artifact.material_path}],
      document_type:"period-digest",output_directory:$output_directory,
      name:($generated[0].artifact.target_date+".md")}
    | select(.material==[{kind:"file",path:$generated[0].artifact.material_path}] and
        .document_type=="period-digest" and (.output_directory|type=="string") and
        .name=="2026-09-02.md" and (has("update_target")|not))' >/dev/null || status=1

  # 対象日に0件ならmaterialも空の最終資料も作らない。
  if (cd "$fixture/non-git" && python3 "$script" --day-index "$fixture/day-index.jsonl" --date 2026-09-03 --out-dir "$fixture/empty") >/dev/null 2>&1; then
    status=1
  fi
  [ ! -e "$fixture/empty" ] || status=1

  # provisionalは完成済み素材ではないため、documentへ進まず停止する。
  jq -c '.provisional=true' "$fixture/day-index.jsonl" > "$fixture/provisional-index.jsonl"
  if (cd "$fixture/non-git" && python3 "$script" --day-index "$fixture/provisional-index.jsonl" --date 2026-09-02 --out-dir "$fixture/provisional") >/dev/null 2>&1; then
    status=1
  fi
  [ ! -e "$fixture/provisional" ] || status=1
  return "$status"
}


validate_session_digest_material_fixture && pass "make-session-digest material.py の生成・cleanup・0件・provisional" || fail "make-session-digest material.py"

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

# ── 消費側の契約lint（G2同期後の共有版）: 外部依存の内部名を消費側の文書・script・設定へ書いていない ──
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
    HARNESS_PLUGIN_DEV_ROOTS="$map" python3 "$ROOT/scripts/lint-consumer-contract.py" --repo "$ROOT" --runtime "$runtime" || status=1
  done
  return "$status"
}
lint_consumer_contract && pass "消費側契約lint（両runtime。依存先の内部名を書いていない）" || fail "消費側契約lint"

if [ "$failed" -eq 0 ]; then echo 'Validation: passed'; else echo 'Validation: failed'; fi
[ "$failed" -eq 0 ]
