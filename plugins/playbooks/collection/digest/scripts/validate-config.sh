#!/usr/bin/env bash
set -euo pipefail
jq -e '(.sources|type=="array" and all(.[]; type=="object" and
    (keys == ["dir"]) and (.dir|type=="string" and length>0))) and
  (.labels|type=="array" and all(.[]; type=="string")) and
  (.output|type=="object" and (.dir|type=="string" and length>0) and
  (.format=="html" or .format=="markdown") and (.theme=="dark" or .theme=="light" or .theme=="auto")) and
  (.digests|type=="array" and all(.[]; type=="object" and
    ((keys - ["include_parts","labels","name","output","period","prompt","type"])|length==0) and
    (.name|type=="string" and test("^[A-Za-z0-9._-]+$")) and
    (.period=="daily" or .period=="weekly" or .period=="monthly") and
    (.type=="period-digest" or .type=="decision-log" or .type=="open-questions") and
    (.prompt|type=="string") and
    ((.include_parts // false)|type=="boolean") and
    ((has("labels")|not) or (.labels|type=="array" and all(.[]; type=="string"))) and
    ((has("output")|not) or (.output|type=="object")))) and
  ([.digests[].name]|length==(unique|length))' "$1" >/dev/null \
  || { echo "[error] digest sources/output/digests schemaが不正" >&2; exit 2; }
