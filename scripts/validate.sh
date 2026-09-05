#!/usr/bin/env bash
# Scenario: repositoryのplugin集合、manifest、marketplace、構文が一致する
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/plugin-repository-validation.XXXXXX") || exit 2
trap 'rm -rf "$TMP_ROOT"' EXIT
failed=0
python3 "$ROOT/scripts/test-hardening.py" || failed=1
python3 "$ROOT/scripts/sync-runtime.py" --check || failed=1
python3 -m unittest discover -s "$ROOT/tests" -p test_collection_integrity.py || failed=1


python3 "$ROOT/scripts/validate-distribution.py" "$ROOT" || failed=1
python3 "$ROOT/scripts/validate-distribution.py" --self-test "$ROOT" || failed=1

validate_dependency_resolution_contract() {
  local resolver="$ROOT/shared/playbook/resolve-dependency.py"
  local fixture="$TMP_ROOT/dependency-resolution"
  local cache="$fixture/empty/.harness-plugin-test-cache"
  local isolated_resolver="$fixture/empty/scripts/resolve-dependency.py"
  local isolated_root
  local status=0
  local out

  mkdir -p "$fixture/empty/scripts" "$cache/fixture-market/fixture-plugin/1.0.0/.codex-plugin" "$cache/fixture-market/fixture-plugin/1.0.0/.claude-plugin"
  cp "$resolver" "$isolated_resolver"
  isolated_root=$(cd "$fixture/empty" && pwd -P)
  mkdir -p "$cache/fixture-market/fixture-plugin/9.9.9/.codex-plugin" "$cache/fixture-market/fixture-plugin/9.9.9/.claude-plugin"
  for version in 1.0.0 9.9.9; do
    printf '{"name":"fixture-plugin","version":"%s"}\n' "$version" > "$cache/fixture-market/fixture-plugin/$version/.codex-plugin/plugin.json"
    printf '{"name":"fixture-plugin","version":"%s"}\n' "$version" > "$cache/fixture-market/fixture-plugin/$version/.claude-plugin/plugin.json"
  done
  printf '%s\n' '---' 'name: wrong-skill' 'description: fixture' '---' > "$cache/fixture-market/fixture-plugin/9.9.9/SKILL.md"

  local marketplace repository_plugin
  marketplace=$(jq -r '.name' "$ROOT/.agents/plugins/marketplace.json")
  repository_plugin=$(jq -r '.plugins[0].name' "$ROOT/.agents/plugins/marketplace.json")
  for runtime in codex claude; do
    out=$(HARNESS_PLUGIN_RUNTIME="$runtime" python3 "$resolver" --plugin-root "$ROOT/shared/playbook" --plugin "$repository_plugin" --marketplace "$marketplace" 2> "$fixture/repository-$runtime.err")
    jq -e --arg runtime "$runtime" --arg plugin "$repository_plugin" '.runtime==$runtime and .plugin==$plugin and .source_kind=="repository"' >/dev/null <<<"$out" || status=1

    out=$(HARNESS_PLUGIN_RUNTIME="$runtime" HARNESS_PLUGIN_CACHE_ROOT="$cache" python3 "$isolated_resolver" --plugin-root "$isolated_root" --plugin fixture-plugin --marketplace fixture-market 2> "$fixture/cache-$runtime.err")
    jq -e --arg runtime "$runtime" '.runtime==$runtime and .version=="9.9.9" and .source_kind=="installed-cache"' >/dev/null <<<"$out" || status=1
  done

  local installed_cache="$fixture/profile/plugins/cache"
  local installed_caller="$installed_cache/caller-market/caller-plugin/1.0.0/playbook"
  mkdir -p "$installed_caller/scripts"
  cp "$resolver" "$installed_caller/scripts/resolve-dependency.py"
  cp -R "$cache/fixture-market" "$installed_cache/"
  local installed_root
  installed_root=$(cd "$installed_caller" && pwd -P)
  for runtime in codex claude; do
    out=$(HARNESS_PLUGIN_RUNTIME="$runtime" python3 "$installed_caller/scripts/resolve-dependency.py" --plugin-root "$installed_root" --plugin fixture-plugin --marketplace fixture-market 2> "$fixture/installed-$runtime.err")
    jq -e --arg runtime "$runtime" '.runtime==$runtime and .version=="9.9.9" and .source_kind=="installed-cache"' >/dev/null <<<"$out" || status=1
  done

  mkdir -p "$fixture/dev/.codex-plugin" "$fixture/dev/.claude-plugin"
  printf '%s\n' '{"name":"fixture-plugin","version":"3.4.5"}' > "$fixture/dev/.codex-plugin/plugin.json"
  printf '%s\n' '{"name":"fixture-plugin","version":"3.4.5"}' > "$fixture/dev/.claude-plugin/plugin.json"
  jq -n --arg root "$fixture/dev" '{schema:1,dependencies:{"fixture-market/fixture-plugin":$root}}' > "$fixture/dev-map.json"
  out=$(HARNESS_PLUGIN_RUNTIME=codex HARNESS_PLUGIN_DEV_ROOTS="$fixture/dev-map.json" HARNESS_PLUGIN_CACHE_ROOT="$cache" python3 "$isolated_resolver" --plugin-root "$isolated_root" --plugin fixture-plugin --marketplace fixture-market 2> "$fixture/dev.err")
  jq -e '.version=="3.4.5" and .source_kind=="dev-map"' >/dev/null <<<"$out" || status=1

  if HARNESS_PLUGIN_RUNTIME=codex HARNESS_PLUGIN_CACHE_ROOT="$cache" python3 "$isolated_resolver" --plugin-root "$isolated_root" --plugin missing-plugin --marketplace fixture-market >/dev/null 2> "$fixture/missing.err"; then
    status=1
  else
    rg '\[error:dependency-missing\].*plugin=missing-plugin.*marketplace=fixture-market' "$fixture/missing.err" >/dev/null || status=1
  fi

  mv "$cache/fixture-market/fixture-plugin/9.9.9/.codex-plugin/plugin.json" "$fixture/correct-manifest.json"
  printf '%s\n' '{"name":"other-plugin","version":"9.9.9"}' > "$cache/fixture-market/fixture-plugin/9.9.9/.codex-plugin/plugin.json"
  if HARNESS_PLUGIN_RUNTIME=codex HARNESS_PLUGIN_CACHE_ROOT="$cache" python3 "$isolated_resolver" --plugin-root "$isolated_root" --plugin fixture-plugin --marketplace fixture-market >/dev/null 2> "$fixture/identity.err"; then
    status=1
  else
    rg 'manifest-identity-mismatch' "$fixture/identity.err" >/dev/null || status=1
  fi
  mv "$fixture/correct-manifest.json" "$cache/fixture-market/fixture-plugin/9.9.9/.codex-plugin/plugin.json"

  mkdir -p "$fixture/ambiguous/.agents/plugins" "$fixture/ambiguous/.claude-plugin" "$fixture/ambiguous/plugins/caller"
  mkdir -p "$fixture/ambiguous/plugins/caller/scripts"
  cp "$resolver" "$fixture/ambiguous/plugins/caller/scripts/resolve-dependency.py"
  local ambiguous_root
  ambiguous_root=$(cd "$fixture/ambiguous/plugins/caller" && pwd -P)
  jq -n '{name:"fixture-market",plugins:[{name:"fixture-plugin",source:{source:"local",path:"./plugins/a"}},{name:"fixture-plugin",source:{source:"local",path:"./plugins/b"}}]}' > "$fixture/ambiguous/.agents/plugins/marketplace.json"
  if HARNESS_PLUGIN_RUNTIME=codex python3 "$fixture/ambiguous/plugins/caller/scripts/resolve-dependency.py" --plugin-root "$ambiguous_root" --plugin fixture-plugin --marketplace fixture-market >/dev/null 2> "$fixture/ambiguous.err"; then
    status=1
  else
    rg 'source_kind=repository reason=marketplace-entry' "$fixture/ambiguous.err" >/dev/null || status=1
  fi

  mkdir -p "$fixture/playbook/scripts" "$fixture/repo"
  local playbook_cache="$fixture/playbook/.harness-plugin-test-cache"
  mkdir -p "$playbook_cache"
  cp -R "$cache/." "$playbook_cache/"
  cp "$ROOT/shared/playbook/resolve.sh" "$fixture/playbook/scripts/resolve.sh"
  cp "$ROOT/shared/playbook/resolve-dependency.py" "$fixture/playbook/scripts/resolve-dependency.py"
  printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$fixture/playbook/scripts/validate-config.sh"
  chmod +x "$fixture/playbook/scripts/resolve.sh" "$fixture/playbook/scripts/validate-config.sh"
  printf '%s\n' 'version: 2' 'name: fixture-playbook' 'description: fixture' 'instructions:' '  execution: {directive: fixture}' 'requires:' '  - {plugin: fixture-plugin, marketplace: fixture-market}' 'steps:' '  - {id: invoke, skill: expected-skill, purpose: fixture}' > "$fixture/playbook/playbook.yml"
  if XDG_CONFIG_HOME="$fixture/config" HARNESS_PLUGIN_RUNTIME=codex HARNESS_PLUGIN_CACHE_ROOT="$playbook_cache" bash "$fixture/playbook/scripts/resolve.sh" "$fixture/repo" >/dev/null 2> "$fixture/skill.err"; then
    status=1
  else
    rg 'steps が指すスキルが requires のプラグインに無い: expected-skill' "$fixture/skill.err" >/dev/null || status=1
  fi

  cp "$fixture/playbook/playbook.yml" "$fixture/playbook/base.yml"
  yq -o=json -I=0 '.' "$fixture/playbook/base.yml" | jq '.requires[0].version="1.0.0"' | yq -P > "$fixture/playbook/playbook.yml"
  if XDG_CONFIG_HOME="$fixture/config" HARNESS_PLUGIN_RUNTIME=codex HARNESS_PLUGIN_CACHE_ROOT="$playbook_cache" bash "$fixture/playbook/scripts/resolve.sh" "$fixture/repo" >/dev/null 2> "$fixture/pin.err"; then status=1; fi
  yq -o=json -I=0 '.' "$fixture/playbook/base.yml" | jq '.requires[0]=.requires[0].plugin' | yq -P > "$fixture/playbook/playbook.yml"
  if XDG_CONFIG_HOME="$fixture/config" HARNESS_PLUGIN_RUNTIME=codex HARNESS_PLUGIN_CACHE_ROOT="$playbook_cache" bash "$fixture/playbook/scripts/resolve.sh" "$fixture/repo" >/dev/null 2> "$fixture/bare.err"; then status=1; fi

  return "$status"
}

validate_session_digest_material_fixture() {
  local fixture="$TMP_ROOT/session-digest-material"
  local script="$ROOT/plugins/playbooks/collection/session-digest/scripts/material.py"
  local material="$fixture/private/session-material-fixture.json"
  local output="$fixture/final.md"
  local index="$fixture/index.jsonl"
  local status=0 out
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
  jq -e '.decision=="written" and (.artifact.material_path|startswith("'"$fixture"'"))' "$fixture/generated.json" >/dev/null || status=1
  return "$status"
}
while IFS= read -r pb; do
  yq -o=json -I=0 '.' "$pb" | jq -e '.version==2 and (.requires|length>0) and all(.requires[]; type=="object" and ((keys|sort)==["marketplace","plugin"]))' >/dev/null || failed=1
  yq -o=json -I=0 '.' "$pb" | jq -e 'all(.requires[]; .marketplace=="collect-and-digest" or .plugin==.marketplace)' >/dev/null || failed=1
  root=$(dirname "$pb")
  cmp -s "$ROOT/shared/playbook/resolve.sh" "$root/scripts/resolve.sh" || failed=1
  cmp -s "$ROOT/shared/playbook/resolve-dependency.py" "$root/scripts/resolve-dependency.py" || failed=1
done < <(find "$ROOT/plugins/playbooks" -name playbook.yml -type f 2>/dev/null | sort)
while IFS= read -r script; do bash -n "$script" || failed=1; done < <(find "$ROOT" -type f -name '*.sh' | sort)
while IFS= read -r script; do PYTHONPYCACHEPREFIX="$TMP_ROOT/pycache" python3 -m py_compile "$script" || failed=1; done < <(find "$ROOT" -type f -name '*.py' | sort)
validate_dependency_resolution_contract || failed=1
validate_session_digest_material_fixture || failed=1
session_digest="$ROOT/plugins/playbooks/collection/session-digest"
if yq -o=json -I=0 '.' "$session_digest/playbook.yml" | jq -e '
    (.requires | any(.plugin=="write-doc" and .marketplace=="write-doc")) and
    (.requires | all(.plugin!="writing-rules")) and
    (.steps | any(.id=="document" and .playbook=="write-doc")) and
    (.steps | any(.id=="material" and (.provides | index("material_path")))) and
    (.steps[-1].id=="cleanup" and .steps[-1].script=="scripts/material.py" and .steps[-1].provides==["cleanup_report"]) and
    (.steps[-1].needs | sort==["index","material_path","path"]) and
    (.steps | all(.id!="draft" and .id!="store"))' >/dev/null \
  && [ ! -e "$session_digest/scripts/store.py" ] \
  && rg -F '最終Markdownの保存は`write-doc`だけが行う' "$session_digest/references/output.md" >/dev/null \
  && rg -F -- '--out-dir ~/.local/state/harness-plugins/session-digest/material' "$session_digest/SKILL.md" >/dev/null \
  && rg -F -- 'material.py" --cleanup' "$session_digest/SKILL.md" >/dev/null \
  && rg -F '出力JSON全体を`cleanup_report`として扱う。cleanupはmaterial file 1件だけをunlinkし、0700の実行専用directoryは残す。' "$session_digest/SKILL.md" "$session_digest/references/output.md" >/dev/null; then
  :
else
  failed=1
fi
if [ "$failed" -eq 0 ]; then echo 'Validation: passed'; else echo 'Validation: failed'; fi
[ "$failed" -eq 0 ]
