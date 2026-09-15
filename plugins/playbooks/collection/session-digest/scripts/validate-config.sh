#!/usr/bin/env bash
set -euo pipefail
jq -e '(.inputs==["user_input"]) and
  ([.steps[].id]==["collect","material","document","cleanup"]) and
  (.steps[0].skill=="collect-sessions" and .steps[0].needs==["user_input"] and .steps[0].provides==["index","target_date","provisional"]) and
  (.steps[1].script=="scripts/material.py" and .steps[1].needs==["index","target_date","provisional"] and .steps[1].provides==["material_path","input_hash","target_date","session_count"]) and
  (.steps[2].playbook=="write-doc" and .steps[2].input=={"document_type":"${.contract.document_type}"} and .steps[2].needs==["material_path","input_hash","target_date","session_count"] and .steps[2].provides==["status","path","reason"]) and
  (.steps[3].script=="scripts/material.py" and .steps[3].needs==["material_path","path","index"] and .steps[3].provides==["cleanup_report"]) and
  all(.steps[]; ([has("agent_work"),has("script"),has("playbook"),has("skill")]|map(select(.))|length)==1) and
  (.output|type=="object") and (.output.dir|type=="string" and length>0) and
  (.output.format=="markdown") and
  (.output.timezone|type=="string" and length>0) and
  (.output.subagents=="exclude" or .output.subagents=="include") and
  (.contract.session_item_fields==["source","source_id","source_path","source_fingerprint","relation","parent_source_id","target_date","display","observed_at","collector"]) and
  (.contract.document_type=="period-digest") and
  (.contract.output_name=="<target_date>.md") and
  ((.output|keys)-["dir","format","timezone","subagents"]|length==0) and
  ((.contract|keys)-["session_item_fields","document_type","output_name"]|length==0)' "$1" >/dev/null \
  || { echo "[error] session-digest output/contractまたはmaterial→write-doc→cleanup配線が不正" >&2; exit 2; }
