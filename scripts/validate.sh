#!/usr/bin/env bash
# Scenario: repositoryのplugin集合、manifest、marketplace、構文が一致する
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/plugin-repository-validation.XXXXXX") || exit 2
TMP_ROOT=$(cd "$TMP_ROOT" && pwd -P) || exit 2
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/locks"
# 利用者環境の解決経路を持ち込まない。必要な検査だけが自分で設定する。
unset HARNESS_PLUGIN_DEV_ROOTS HARNESS_PLUGIN_CACHE_ROOT
OWN_MARKETPLACE=$(jq -r '.metadata.harness.marketplace // ""' "$ROOT/plugins/.claude-plugin/plugin.json")
[ -n "$OWN_MARKETPLACE" ] || { echo '[validate] metadata.harness.marketplace を宣言していない' >&2; exit 2; }
failed=0
python3 "$ROOT/scripts/test-hardening.py" || failed=1
python3 "$ROOT/scripts/sync-runtime.py" --check || failed=1
# lockだけでなく**正本そのもの**と突き合わせる。兄弟checkoutが無ければ失敗させる。
# **兄弟repositoryは読むだけである。** この検査もこの下の実配布物解決も、
# ../*-plugins へ書き込まず、mv / rename / rm もしない。
# 「兄弟が無いと失敗する」ことを確かめたいときは、兄弟を動かすのではなく、
# 一時directoryへ自repositoryを複製して（兄弟の無い場所で）このscriptを実行する。
RUNTIME_SOURCE="$ROOT/../product-planning-plugins/shared/runtime-source"
if [ -d "$RUNTIME_SOURCE" ]; then
  python3 "$ROOT/scripts/sync-runtime.py" --check --source "$RUNTIME_SOURCE" >/dev/null \
    || { echo '[validate] runtime複製が正本とずれている（--source つき --check）' >&2; failed=1; }
else
  echo '[validate] runtime正本が兄弟checkoutに無い: ../product-planning-plugins/shared/runtime-source' >&2
  failed=1
fi
python3 -m unittest discover -s "$ROOT/tests" -p test_collection_integrity.py || failed=1


python3 "$ROOT/scripts/validate-distribution.py" "$ROOT" || failed=1
python3 "$ROOT/scripts/validate-distribution.py" --self-test "$ROOT" || failed=1

# owning_bundle は所属package宣言から内外を判定する。合成fixtureの呼び出し元にも
# bundle manifest（marketplace 宣言）が要る。
write_bundle_manifest() {
  local dir="$1" name="$2" market="$3" internals="${4:-{\}}"
  local runtime
  for runtime in codex claude; do
    mkdir -p "$dir/.$runtime-plugin"
    jq -n --arg n "$name" --arg m "$market" --argjson i "$internals" \
      '{name:$n,version:"1.0.0",metadata:{harness:{installationSurface:"playbook-package",marketplace:$m,internalPlugins:$i,contractVersion:1}}}' \
      > "$dir/.$runtime-plugin/plugin.json"
  done
}

validate_dependency_resolution_contract() {
  local resolver="$ROOT/shared/playbook/resolve-dependency.py"
  local repo_resolver="$ROOT/plugins/playbooks/collection/session-digest/scripts/resolve-dependency.py"
  local repo_root="$ROOT/plugins/playbooks/collection/session-digest"
  local fixture="$TMP_ROOT/dependency-resolution"
  local cache="$fixture/empty/.harness-plugin-test-cache"
  local isolated_resolver="$fixture/empty/scripts/resolve-dependency.py"
  local isolated_root
  local status=0
  local out

  mkdir -p "$fixture/empty/scripts" "$cache/fixture-market/fixture-plugin/1.0.0/.codex-plugin" "$cache/fixture-market/fixture-plugin/1.0.0/.claude-plugin"
  cp "$resolver" "$isolated_resolver"
  isolated_root=$(cd "$fixture/empty" && pwd -P)
  write_bundle_manifest "$isolated_root" caller-plugin caller-market
  mkdir -p "$cache/fixture-market/fixture-plugin/9.9.9/.codex-plugin" "$cache/fixture-market/fixture-plugin/9.9.9/.claude-plugin"
  # 外部依存は公開playbookのimplementsを宣言していないと解決できない。
  # cache fixtureも実物と同じ形（marketplace / playbooks / implements と公開入口4点）にする。
  for version in 1.0.0 9.9.9; do
    local versioned="$cache/fixture-market/fixture-plugin/$version"
    mkdir -p "$versioned/pb/scripts"
    printf '%s\n' '---' 'name: fixture-entry' 'description: fixture' '---' > "$versioned/pb/SKILL.md"
    printf '%s\n' 'version: 2' 'name: pb' 'description: fixture' 'instructions: {execution: {directive: fixture}}' 'requires: []' 'steps: [{id: work, skill: fixture-entry, purpose: fixture}]' > "$versioned/pb/playbook.yml"
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$versioned/pb/scripts/resolve.sh"
    printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$versioned/pb/scripts/prepare.sh"
    for runtime in codex claude; do
      jq -n --arg v "$version" '{name:"fixture-plugin",version:$v,metadata:{harness:{installationSurface:"playbook-package",marketplace:"fixture-market",playbooks:{pb:"./pb"},internalPlugins:{},contractVersion:1,implements:[{id:"fixture-market/fixture-plugin",version:1,kind:"playbook",playbook:"pb"}]}}}' \
        > "$versioned/.$runtime-plugin/plugin.json"
    done
  done
  printf '%s\n' '---' 'name: wrong-skill' 'description: fixture' '---' > "$cache/fixture-market/fixture-plugin/9.9.9/SKILL.md"

  local marketplace repository_plugin
  marketplace=$(jq -r '.name' "$ROOT/.agents/plugins/marketplace.json")
  repository_plugin=$(jq -r '.plugins[0].name' "$ROOT/.agents/plugins/marketplace.json")
  for runtime in codex claude; do
    out=$(HARNESS_PLUGIN_RUNTIME="$runtime" python3 "$repo_resolver" --plugin-root "$repo_root" --plugin "$repository_plugin" --marketplace "$marketplace" 2> "$fixture/repository-$runtime.err")
    jq -e '.dependency_scope=="internal"' >/dev/null <<<"$out" || status=1
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
  write_bundle_manifest "$installed_root" caller-plugin caller-market
  for runtime in codex claude; do
    out=$(HARNESS_PLUGIN_RUNTIME="$runtime" python3 "$installed_caller/scripts/resolve-dependency.py" --plugin-root "$installed_root" --plugin fixture-plugin --marketplace fixture-market 2> "$fixture/installed-$runtime.err")
    jq -e --arg runtime "$runtime" '.runtime==$runtime and .version=="9.9.9" and .source_kind=="installed-cache"' >/dev/null <<<"$out" || status=1
  done

  mkdir -p "$fixture/dev/.codex-plugin" "$fixture/dev/.claude-plugin" "$fixture/dev/pb/scripts"
  printf '%s\n' '---' 'name: fixture-entry' 'description: fixture' '---' > "$fixture/dev/pb/SKILL.md"
  printf '%s\n' 'version: 2' 'name: pb' 'description: fixture' 'instructions: {execution: {directive: fixture}}' 'requires: []' 'steps: [{id: work, skill: fixture-entry, purpose: fixture}]' > "$fixture/dev/pb/playbook.yml"
  printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$fixture/dev/pb/scripts/resolve.sh"
  printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$fixture/dev/pb/scripts/prepare.sh"
  for runtime in codex claude; do
    jq -n '{name:"fixture-plugin",version:"3.4.5",metadata:{harness:{installationSurface:"playbook-package",marketplace:"fixture-market",playbooks:{pb:"./pb"},internalPlugins:{},contractVersion:1,implements:[{id:"fixture-market/fixture-plugin",version:1,kind:"playbook",playbook:"pb"}]}}}' \
      > "$fixture/dev/.$runtime-plugin/plugin.json"
  done
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
  write_bundle_manifest "$fixture/ambiguous/plugins" caller-plugin caller-market
  jq -n '{name:"fixture-market",plugins:[{name:"fixture-plugin",source:{source:"local",path:"./plugins/a"}},{name:"fixture-plugin",source:{source:"local",path:"./plugins/b"}}]}' > "$fixture/ambiguous/.agents/plugins/marketplace.json"
  if HARNESS_PLUGIN_RUNTIME=codex python3 "$fixture/ambiguous/plugins/caller/scripts/resolve-dependency.py" --plugin-root "$ambiguous_root" --plugin fixture-plugin --marketplace fixture-market >/dev/null 2> "$fixture/ambiguous.err"; then
    status=1
  else
    rg 'source_kind=repository reason=marketplace-entry' "$fixture/ambiguous.err" >/dev/null || status=1
  fi

  mkdir -p "$fixture/playbook/scripts" "$fixture/repo" "$fixture/playbook/internal"
  local playbook_cache="$fixture/playbook/.harness-plugin-test-cache"
  mkdir -p "$playbook_cache"
  cp -R "$cache/." "$playbook_cache/"
  # 内部依存として解決させる。外部依存なら implements 宣言が要るので、
  # steps の skill 検査へ到達する前に external-dependency-no-playbook で落ちる。
  write_bundle_manifest "$fixture/playbook" caller-plugin fixture-market '{"fixture-plugin":"./internal"}'
  for runtime in codex claude; do
    mkdir -p "$fixture/playbook/internal/.$runtime-plugin"
    printf '%s\n' '{"name":"fixture-plugin","version":"1.0.0"}' > "$fixture/playbook/internal/.$runtime-plugin/plugin.json"
  done
  printf '%s\n' '---' 'name: wrong-skill' 'description: fixture' '---' > "$fixture/playbook/internal/SKILL.md"
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
# ── 消費側の依存契約 ───────────────────────────────────────────
# 依存先から使ってよいのは公開playbookの入口だけである。
# 静的（lint）と解決（resolver）の両輪で強制し、**fixtureだけで緑にしない**。
# 実配布物（兄弟checkoutの <marketplace>-plugins/plugins）が手元にあるときは、
# 合成providerではなくそれに対して解決する。

# 自分のmarketplace以外を要求している依存を、全playbookから集める。
external_contracts() {
  local pb
  while IFS= read -r pb; do
    yq -o=json -I=0 '.' "$pb" \
      | jq -r --arg own "$OWN_MARKETPLACE" \
          '.requires[] | select(.marketplace != $own) | "\(.marketplace)\t\(.plugin)"'
  done < <(find "$ROOT/plugins" -name playbook.yml -type f | sort) | sort -u
}

# 実配布物を指す開発mapを作る。**兄弟checkoutが無ければ失敗させる。**
# fixtureで代用すると、実物との乖離が緑のまま残る。
provider_dev_map=""
provider_missing=""
build_provider_dev_map() {
  local map="$TMP_ROOT/provider-dev-map.json" entries='{}' market plugin package name
  while IFS=$'\t' read -r market plugin; do
    [ -n "$market" ] || continue
    package="$ROOT/../${market}-plugins/plugins"
    if [ ! -f "$package/.claude-plugin/plugin.json" ] || [ ! -f "$package/.codex-plugin/plugin.json" ]; then
      provider_missing="${provider_missing} ${market}/${plugin}"
      continue
    fi
    name=$(jq -r '.name // ""' "$package/.claude-plugin/plugin.json")
    if [ "$name" != "$plugin" ]; then
      provider_missing="${provider_missing} ${market}/${plugin}"
      continue
    fi
    package=$(cd "$package" && pwd -P) || return 1
    entries=$(jq -c --arg k "${market}/${plugin}" --arg v "$package" '.[$k]=$v' <<<"$entries") || return 1
  done < <(external_contracts)
  jq -n --argjson d "$entries" '{schema:1,dependencies:$d}' > "$map" || return 1
  [ "$entries" = '{}' ] || provider_dev_map="$map"
  if [ -n "$provider_missing" ]; then
    echo "[validate] 依存先の実配布物が兄弟checkoutに無い:${provider_missing}" >&2
    echo "[validate]   ../<marketplace>-plugins/plugins を用意してから実行すること" >&2
    return 1
  fi
  return 0
}

# (A) lint — 文書・設定・scriptの全行に依存先の内部の作りが漏れていないか。
# 内部名は実配布物のmanifestから生成する。除外は無い。1件でも落とす。
validate_consumer_contract_lint() {
  local status=0 runtime out filter rc
  filter='(.findings | length) == 0'
  for runtime in claude codex; do
    # exit 1 は「違反あり」なので出力を必ず受け取る。2 以上だけが実行不能である。
    out=$(HARNESS_PLUGIN_DEV_ROOTS="$provider_dev_map" \
      python3 "$ROOT/scripts/lint-consumer-contract.py" --repo "$ROOT" --runtime "$runtime" --json)
    rc=$?
    if [ "$rc" -ge 2 ]; then
      echo "[validate] lintが実行できない($runtime)" >&2; status=1; continue
    fi
    if ! jq -e "$filter" >/dev/null <<<"$out"; then
      status=1
      jq -r --arg rt "$runtime" '.findings[]
        | "[lint:\($rt)] [\(.code)] \(.file):\(.line) \(.detail)"' <<<"$out" >&2
    fi
  done
  return "$status"
}

# (B) 実配布物に対する解決 — 兄弟checkoutのproviderを開発mapで指し、両runtimeで解決する。
validate_real_provider_resolution() {
  local status=0 runtime pb name out json dep_root dep_entry dep_entry_skill entry declared
  if [ -z "$provider_dev_map" ]; then
    echo '[validate] 実配布物への開発mapが作れていない' >&2
    return 1
  fi
  for runtime in claude codex; do
    while IFS= read -r pb; do
      name=$(basename "$(dirname "$pb")")
      if ! out=$(TMPDIR="$TMP_ROOT/locks" HARNESS_PLUGIN_RUNTIME="$runtime" \
                 HARNESS_PLUGIN_DEV_ROOTS="$provider_dev_map" \
                 bash "$(dirname "$pb")/scripts/resolve.sh" "$ROOT" 2> "$TMP_ROOT/real-$runtime-$name.err"); then
        echo "[validate] 実配布物に対して${name}が解決できない($runtime): $(head -1 "$TMP_ROOT/real-$runtime-$name.err")" >&2
        status=1
        continue
      fi
      # 外部依存として解決され、契約を実装し、公開面が入口だけに閉じていること。
      json=$(yq -o=json -I=0 '.' <<<"$out") || { status=1; continue; }
      jq -e '
        ([.deps[] | select(.dependency_scope == "external")]) as $ext
        | ($ext | length) > 0
        and (.resolution.bindings_lock | type == "string")
        and all($ext[]; . as $d
          | ($d.contract | type == "string")
          and (($d.implements
                | map(select(.id == $d.contract and .version == 1 and .kind == "playbook"))
                | length) == 1)
          and ($d.entry | type == "string")
          and ($d.entry_skill | type == "string"))' >/dev/null <<<"$json" \
        || { echo "[validate] ${name}($runtime)の解決結果が契約の形になっていない" >&2; status=1; }
      # 公開面は .root 直下の3点と .entry だけ。entry は入口SKILL.mdの実pathで、
      # entry_skill はその front matter の name と一致すること。
      while IFS=$'\t' read -r dep_root dep_entry dep_entry_skill; do
        [ -n "$dep_root" ] || continue
        for entry in playbook.yml scripts/resolve.sh scripts/prepare.sh SKILL.md; do
          [ -f "$dep_root/$entry" ] || { echo "[validate] 公開面の入口が無い: $dep_root/$entry" >&2; status=1; }
        done
        [ -f "$dep_entry" ] || { echo "[validate] entryが実ファイルでない: $dep_entry" >&2; status=1; }
        [ "$dep_entry" = "$dep_root/SKILL.md" ] \
          || { echo "[validate] entryが入口SKILL.mdを指していない: $dep_entry" >&2; status=1; }
        declared=$(awk 'NR>1 && /^---$/{exit} /^name: /{sub(/^name: /,""); gsub(/["'"'"']/,""); print}' "$dep_entry" 2>/dev/null)
        [ "$declared" = "$dep_entry_skill" ] \
          || { echo "[validate] entry_skillが入口SKILL.mdのnameと違う: $dep_entry_skill != $declared" >&2; status=1; }
      done < <(jq -r '.deps[] | select(.dependency_scope == "external")
                      | [.root, .entry, .entry_skill] | @tsv' <<<"$json")
    done < <(find "$ROOT/plugins" -name playbook.yml -type f | sort)
  done
  return "$status"
}

# (C) 負の試験 — 契約を宣言する合成providerを立て、規則違反が必ず落ちることを見る。
# 実配布物の有無に関係なく走らせる。ここで見るのは*我々の*playbookの形と、
# resolverが規則を強制することであって、providerの中身ではない。
validate_contract_enforcement() {
  local fixture="$TMP_ROOT/contract-enforcement"
  local stub="$fixture/provider/write-doc"
  local probe="$fixture/probe/plugins/playbooks/probe"
  local map="$fixture/dev-map.json"
  local status=0 runtime name pb

  mkdir -p "$stub/playbooks/write-doc/scripts" "$stub/.claude-plugin" "$stub/.codex-plugin" \
           "$probe/scripts" "$fixture/probe/plugins/.claude-plugin" "$fixture/probe/plugins/.codex-plugin" \
           "$fixture/repo" "$TMP_ROOT/locks"
  stub=$(cd "$stub" && pwd -P) || return 1
  stub_manifest() { # stub_manifest <jq式>
    local runtime
    for runtime in claude codex; do
      jq "$1" > "$stub/.${runtime}-plugin/plugin.json" <<'JSON' || return 1
{"name":"write-doc","version":"4.0.0","description":"契約v1だけを実装する試験用provider",
 "skills":["./playbooks/write-doc"],
 "metadata":{"harness":{"installationSurface":"playbook-package","marketplace":"write-doc",
 "entryRoot":"./playbooks/write-doc","playbooks":{"write-doc":"./playbooks/write-doc"},
 "internalPlugins":{},"contractVersion":1,
 "implements":[{"id":"write-doc/write-doc","version":1,"kind":"playbook","playbook":"write-doc",
 "types":["period-digest","decision-log","open-questions"]}]}}}
JSON
    done
  }
  printf -- '---\nname: write-doc\ndescription: fixture\n---\nfixture\n' > "$stub/playbooks/write-doc/SKILL.md"
  printf '%s\n' 'version: 2' 'name: write-doc' 'description: fixture' > "$stub/playbooks/write-doc/playbook.yml"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$stub/playbooks/write-doc/scripts/prepare.sh"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$stub/playbooks/write-doc/scripts/resolve.sh"
  stub_manifest '.' || return 1
  jq -n --arg r "$stub" '{schema:1,dependencies:{"write-doc/write-doc":$r}}' > "$map" || return 1

  # (C-1) 我々の実playbookが、契約を実装したproviderに対して両runtimeで解決できる。
  for runtime in claude codex; do
    while IFS= read -r pb; do
      name=$(basename "$(dirname "$pb")")
      TMPDIR="$TMP_ROOT/locks" HARNESS_PLUGIN_RUNTIME="$runtime" HARNESS_PLUGIN_DEV_ROOTS="$map" \
        bash "$(dirname "$pb")/scripts/resolve.sh" "$ROOT" > "$fixture/$name-$runtime.yml" 2> "$fixture/$name-$runtime.err" \
        || { echo "[validate] 契約provider相手に${name}が解決できない($runtime): $(head -1 "$fixture/$name-$runtime.err")" >&2; status=1; }
    done < <(find "$ROOT/plugins" -name playbook.yml -type f | sort)
  done
  # session-digest は型を静的に宣言しているので、能力検査を通っていること。
  yq -er '.playbook.steps[] | select(.id=="document") | .input.document_type' \
    "$fixture/session-digest-claude.yml" >/dev/null 2>&1 \
    || { echo '[validate] session-digestのdocument工程がinput.document_typeを持たない' >&2; status=1; }

  # (C-2) 契約を実装しないproviderは受け付けない。
  stub_manifest 'del(.metadata.harness.implements)' || return 1
  if TMPDIR="$TMP_ROOT/locks" HARNESS_PLUGIN_DEV_ROOTS="$map" \
     bash "$ROOT/plugins/playbooks/collection/session-digest/scripts/resolve.sh" "$ROOT" \
     >/dev/null 2> "$fixture/no-implements.err"; then
    echo '[validate] implementsを持たない依存先を受け入れてしまう' >&2; status=1
  elif ! rg -q 'external-dependency-no-playbook' "$fixture/no-implements.err"; then
    echo "[validate] implements未宣言を期待した理由で拒否できない: $(head -1 "$fixture/no-implements.err")" >&2; status=1
  fi

  # (C-3) 宣言していない文書型は渡せない。
  stub_manifest '.metadata.harness.implements[0].types=["decision-log"]' || return 1
  if TMPDIR="$TMP_ROOT/locks" HARNESS_PLUGIN_DEV_ROOTS="$map" \
     bash "$ROOT/plugins/playbooks/collection/session-digest/scripts/resolve.sh" "$ROOT" \
     >/dev/null 2> "$fixture/capability.err"; then
    echo '[validate] 依存先が実装しない文書型を渡せてしまう' >&2; status=1
  elif ! rg -q 'binding-capability-unsupported' "$fixture/capability.err"; then
    echo "[validate] 未実装の文書型を期待した理由で拒否できない: $(head -1 "$fixture/capability.err")" >&2; status=1
  fi
  stub_manifest '.' || return 1

  # (C-4) 公開面4点以外の触り方は、どの形でも落ちる。
  local runtime_scripts="$ROOT/shared"
  for runtime in claude codex; do
    jq -n '{name:"probe",version:"1.0.0",description:"fixture",skills:["./playbooks/probe"],
      metadata:{harness:{installationSurface:"playbook-package",marketplace:"probe",
      entryRoot:"./playbooks/probe",playbooks:{probe:"./playbooks/probe"},
      internalPlugins:{},contractVersion:1,
      implements:[{id:"probe/probe",version:1,kind:"playbook",playbook:"probe"}]}}}' \
      > "$fixture/probe/plugins/.${runtime}-plugin/plugin.json" || return 1
  done
  printf -- '---\nname: probe\ndescription: fixture\n---\nfixture\n' > "$probe/SKILL.md"
  cp "$runtime_scripts/prepare.sh" "$probe/scripts/prepare.sh"
  cp "$runtime_scripts/run-config.py" "$probe/scripts/run-config.py"
  cp "$runtime_scripts/playbook/resolve.sh" "$probe/scripts/resolve.sh"
  cp "$runtime_scripts/playbook/resolve-dependency.py" "$probe/scripts/resolve-dependency.py"
  cp "$runtime_scripts/playbook/state.py" "$probe/scripts/state.py"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$probe/scripts/validate-config.sh"
  chmod 755 "$probe/scripts"/*

  probe_steps() { # probe_steps <stepのYAML断片>
    { printf '%s\n' 'version: 2' 'name: probe' 'description: fixture' 'instructions:' \
        '  execution: {directive: fixture}' 'requires:' \
        '  - {plugin: write-doc, marketplace: write-doc}' 'steps:'
      cat
    } > "$probe/playbook.yml"
  }
  probe_run() {
    TMPDIR="$TMP_ROOT/locks" XDG_CONFIG_HOME="$fixture/config" HARNESS_PLUGIN_DEV_ROOTS="$map" \
      bash "$probe/scripts/resolve.sh" "$fixture/repo" 2> "$fixture/probe.err"
  }
  probe_expect() { # probe_expect <期待するcode> <説明>
    if probe_run >/dev/null; then
      echo "[validate] $2 を通してしまう" >&2; status=1
    elif ! rg -q "$1" "$fixture/probe.err"; then
      echo "[validate] $2 を期待した理由で拒否できない: $(head -1 "$fixture/probe.err")" >&2; status=1
    fi
  }

  probe_steps <<'YML'
  - {id: document, playbook: write-doc, purpose: fixture, input: {document_type: period-digest}, provides: [path]}
YML
  probe_run >/dev/null || { echo "[validate] 契約どおりのplaybook stepが通らない: $(head -1 "$fixture/probe.err")" >&2; status=1; }

  probe_steps <<'YML'
  - {id: document, skill: write-doc, purpose: fixture, provides: [path]}
YML
  probe_expect 'external-dependency-skill' '外部依存を skill: で呼ぶstep'

  probe_steps <<'YML'
  - {id: document, script: scripts/write.sh, plugin: write-doc, purpose: fixture, provides: [path]}
YML
  probe_expect 'external-dependency-script' '外部依存の script を実行するstep'

  # 禁じた参照の綴りをこのファイルへ直書きすると lint 自身が落ちるので、実行時に組み立てる。
  local head='${.deps.write-doc'
  local forbidden="${head}.root}/scripts/not-an-entry.sh"
  probe_steps <<YML
  - {id: document, playbook: write-doc, purpose: "${forbidden} を実行する", provides: [path]}
YML
  probe_expect 'external-dependency-path' '公開面4点以外の外部path組み立て'

  probe_steps <<'YML'
  - {id: document, playbook: write-doc, purpose: fixture, input: {document_type: no-such-type}, provides: [path]}
YML
  probe_expect 'binding-capability-unsupported' '依存先が実装しない文書型'

  return "$status"
}

while IFS= read -r pb; do
  yq -o=json -I=0 '.' "$pb" | jq -e '.version==2 and (.requires|length>0) and all(.requires[]; type=="object" and ((keys|sort)==["marketplace","plugin"]))' >/dev/null || failed=1
  yq -o=json -I=0 '.' "$pb" | jq -e 'all(.requires[]; .marketplace=="collect-and-digest" or .plugin==.marketplace)' >/dev/null || failed=1
  root=$(dirname "$pb")
  cmp -s "$ROOT/shared/playbook/resolve.sh" "$root/scripts/resolve.sh" || failed=1
  cmp -s "$ROOT/shared/playbook/resolve-dependency.py" "$root/scripts/resolve-dependency.py" || failed=1
  cmp -s "$ROOT/shared/playbook/state.py" "$root/scripts/state.py" || failed=1
  cmp -s "$ROOT/shared/prepare.sh" "$root/scripts/prepare.sh" || failed=1
  cmp -s "$ROOT/shared/run-config.py" "$root/scripts/run-config.py" || failed=1
done < <(find "$ROOT/plugins/playbooks" -name playbook.yml -type f 2>/dev/null | sort)
while IFS= read -r script; do bash -n "$script" || failed=1; done < <(find "$ROOT" -type f -name '*.sh' | sort)
while IFS= read -r script; do PYTHONPYCACHEPREFIX="$TMP_ROOT/pycache" python3 -m py_compile "$script" || failed=1; done < <(find "$ROOT" -type f -name '*.py' | sort)
validate_dependency_resolution_contract || failed=1
validate_session_digest_material_fixture || failed=1
session_digest="$ROOT/plugins/playbooks/collection/session-digest"
if yq -o=json -I=0 '.' "$session_digest/playbook.yml" | jq -e '
    (.requires | any(.plugin=="write-doc" and .marketplace=="write-doc")) and
    (.requires | all(.marketplace=="write-doc" or .marketplace=="collect-and-digest")) and
    (.steps | any(.id=="document" and .playbook=="write-doc"
                  and .input.document_type=="${.contract.document_type}")) and
    (.steps | any(.id=="material" and (.provides | index("material_path")))) and
    (.steps[-1].id=="cleanup" and .steps[-1].script=="scripts/material.py" and .steps[-1].provides==["cleanup_report"]) and
    (.steps[-1].needs | sort==["index","material_path","path"]) and
    ([.steps[].id] == ["collect","material","document","cleanup"])' >/dev/null \
  && [ ! -e "$session_digest/scripts/store.py" ] \
  && rg -F '最終Markdownの保存は`write-doc`だけが行う' "$session_digest/references/output.md" >/dev/null \
  && rg -F -- '--out-dir ~/.local/state/harness-plugins/session-digest/material' "$session_digest/SKILL.md" >/dev/null \
  && rg -F -- 'material.py" --cleanup' "$session_digest/SKILL.md" >/dev/null \
  && rg -F '出力JSON全体を`cleanup_report`として扱う。cleanupはmaterial file 1件だけをunlinkし、0700の実行専用directoryは残す。' "$session_digest/SKILL.md" "$session_digest/references/output.md" >/dev/null; then
  :
else
  failed=1
fi
build_provider_dev_map || failed=1
validate_consumer_contract_lint || failed=1
validate_real_provider_resolution || failed=1
validate_contract_enforcement || failed=1
if [ "$failed" -eq 0 ]; then echo 'Validation: passed'; else echo 'Validation: failed'; fi
[ "$failed" -eq 0 ]
