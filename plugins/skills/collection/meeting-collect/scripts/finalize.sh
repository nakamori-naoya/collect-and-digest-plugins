#!/usr/bin/env bash
# meeting-collect 固有の検査と、出す形の組み立て。
#
# **resolve.sh から source される。** 設定の解決手順は共通なのでここには無い。
# 使えるもの: merged / required / root / PLUGIN_ROOT / name / selected / source / explain / resolve_path
# やること: 固有schemaの検査と、out への最終JSONの代入。
jq -e '.version == 1 and (.notes_dir|type=="string" and length>0) and (.timezone|type=="string" and length>0) and
  (.collect.transcript|type=="boolean") and
  (.collect.max_bytes|type=="number" and floor==. and .>0) and
  (.collect.sources|type=="object") and
  (all(.collect.sources[]; type=="object" and (.enabled|type=="boolean"))) and
  (.instructions.collection.directive|type=="string" and length>0)' >/dev/null <<<"$merged" \
  || { echo "[error] meeting-collect設定の型または値が不正" >&2; exit 2; }
jq -e '([.collect.sources|keys[]] - ["notion","google_docs"] | length)==0' >/dev/null <<<"$merged" \
  || { echo "[error] collect.sources に未知のsourceがある" >&2; exit 2; }
jq -e '((.collect|keys)-["sources","transcript","max_bytes"]|length==0) and
  ((.collect.sources.notion|keys)-["enabled"]|length==0) and
  ((.collect.sources.google_docs|keys)-["enabled","drive_query"]|length==0) and
  ((.collect.sources.google_docs|has("drive_query")|not) or (.collect.sources.google_docs.drive_query|type=="string"))' >/dev/null <<<"$merged" \
  || { echo "[error] collect/sourceの未知キーまたは型が不正" >&2; exit 2; }
timezone=$(jq -r '.timezone' <<<"$merged")
python3 -c 'import sys; from zoneinfo import ZoneInfo; ZoneInfo(sys.argv[1])' "$timezone" 2>/dev/null \
  || { echo "[error] timezone が不正: $timezone" >&2; exit 2; }

notes_dir=$(jq -r '.notes_dir' <<<"$merged")
notes_dir="${notes_dir/#\~/$HOME}"
# 相対パスはリポジトリ root 基準で解決する。プロセスの cwd 基準にすると
# どこから呼ばれたかで保存先が変わり、収集物が散る。
case "$notes_dir" in
  /*) ;;
  *) notes_dir="${root}/${notes_dir}" ;;
esac
merged=$(jq -c --arg d "$notes_dir" --arg root "$root" --arg plugin "$PLUGIN_ROOT" \
  '.notes_dir = $d | .repo_root = $root | .plugin_root = $plugin' <<<"$merged")

out="$merged"
