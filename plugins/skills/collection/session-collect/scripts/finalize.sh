#!/usr/bin/env bash
# session-collect 固有の設定検査と解決済み設定の組み立て。
jq -e '.version==1 and (.state_dir|type=="string" and length>0) and
  (.timezone|type=="string" and length>0) and
  (.sources|type=="object") and
  (.sources.claude_code|type=="object") and (.sources.codex|type=="object") and
  (all(.sources[]; (.enabled|type=="boolean") and (.root|type=="string" and length>0))) and
  (.collection.include_subagents|type=="boolean") and
  (all([.collection.max_scan_files,.collection.max_source_bytes,.collection.stable_read_retries,.collection.quiescent_after_minutes][];
    type=="number" and floor==. and .>0)) and
  (.instructions.collection.directive|type=="string" and length>0)' >/dev/null <<<"$merged" \
  || { echo "[error] session-collect設定の型または値が不正" >&2; exit 2; }
jq -e '((keys-["version","state_dir","timezone","sources","collection","instructions"]|length)==0) and
  ((.sources|keys)-["claude_code","codex"]|length==0) and
  (all(.sources[]; ((keys-["enabled","root"]|length)==0))) and
  ((.collection|keys)-["include_subagents","max_scan_files","max_source_bytes","stable_read_retries","quiescent_after_minutes"]|length==0) and
  ((.instructions|keys)-["collection"]|length==0) and
  ((.instructions.collection|keys)-["directive"]|length==0)' >/dev/null <<<"$merged" \
  || { echo "[error] session-collect設定に未知のキーがある" >&2; exit 2; }
jq -e '[.sources[].enabled] | any' >/dev/null <<<"$merged" \
  || { echo "[error] sourceを1つ以上有効にすること" >&2; exit 2; }
timezone=$(jq -r '.timezone' <<<"$merged")
python3 -c 'import sys; from zoneinfo import ZoneInfo; ZoneInfo(sys.argv[1])' "$timezone" 2>/dev/null \
  || { echo "[error] timezone が不正: ${timezone}" >&2; exit 2; }
state_dir=$(jq -r '.state_dir' <<<"$merged"); state_dir="${state_dir/#\~/$HOME}"
case "$state_dir" in /*) ;; *) state_dir="${root}/${state_dir}" ;; esac
claude_root=$(jq -r '.sources.claude_code.root' <<<"$merged"); claude_root="${claude_root/#\~/$HOME}"
codex_root=$(jq -r '.sources.codex.root' <<<"$merged"); codex_root="${codex_root/#\~/$HOME}"
merged=$(jq -c --arg d "$state_dir" --arg c "$claude_root" --arg x "$codex_root" \
  --arg root "$root" --arg plugin "$PLUGIN_ROOT" \
  '.state_dir=$d | .sources.claude_code.root=$c | .sources.codex.root=$x |
   .repo_root=$root | .plugin_root=$plugin' <<<"$merged")
out="$merged"
