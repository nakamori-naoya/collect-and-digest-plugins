#!/usr/bin/env bash
set -euo pipefail
jq -e '(.output|type=="object") and (.output.dir|type=="string" and length>0) and
  (.output.format=="markdown") and
  (.output.timezone|type=="string" and length>0) and
  (.output.max_chars_per_session|type=="number" and floor==. and .>0) and
  (.output.subagents=="exclude" or .output.subagents=="include") and
  (.contract.session_item_fields==["source","source_id","source_path","source_fingerprint","relation","parent_source_id","target_date","display","observed_at","collector"]) and
  ((.output|keys)-["dir","format","timezone","max_chars_per_session","subagents"]|length==0) and
  ((.contract|keys)-["session_item_fields"]|length==0)' "$1" >/dev/null \
  || { echo "[error] session-digest output/contract schemaが不正" >&2; exit 2; }
