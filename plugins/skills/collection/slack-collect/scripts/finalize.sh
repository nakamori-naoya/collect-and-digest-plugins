#!/usr/bin/env bash
# slack-collect 固有の検査と、出す形の組み立て。
#
# **resolve.sh から source される。** 設定の解決手順は共通なのでここには無い。
# 使えるもの: merged / required / root / PLUGIN_ROOT / name / selected / source / explain / resolve_path
# やること: 固有schemaの検査と、out への最終JSONの代入。
jq -e '.version == 1 and (.slack_dir|type=="string" and length>0) and (.timezone|type=="string" and length>0) and
  (.collect.max_bytes|type=="number" and floor==. and .>0) and
  (.collect.credential_redaction|type=="boolean") and
  (.instructions.collection.directive|type=="string" and length>0) and
  ((.collect|keys)-["channels","targets","groups","max_bytes","credential_redaction"]|length==0) and
  ((.collect.targets|keys)-["channel_messages","direct_mentions","group_mentions","authored_threads"]|length==0)' >/dev/null <<<"$merged" \
  || { echo "[error] slack-collect設定の型または値が不正" >&2; exit 2; }
timezone=$(jq -r '.timezone' <<<"$merged")
python3 -c 'import sys; from zoneinfo import ZoneInfo; ZoneInfo(sys.argv[1])' "$timezone" 2>/dev/null \
  || { echo "[error] timezone が不正: $timezone" >&2; exit 2; }

channels_type=$(jq -r '.collect.channels | type' <<<"$merged")
case "$channels_type" in
  string)
    [ "$(jq -r '.collect.channels' <<<"$merged")" = "all" ] \
      || { echo "[error] collect.channels の文字列は all だけを許す" >&2; exit 2; }
    jq -e '.collect.targets.channel_messages == false' >/dev/null <<<"$merged" \
      || { echo "[error] collect.channels: all では channel_messages: false が必須（全チャンネル全投稿は収集しない）" >&2; exit 2; }
    ;;
  array)
    [ "$(jq '.collect.channels | length' <<<"$merged")" -gt 0 ] \
      || { echo "[error] collect.channels は all または1件以上のチャンネルを明示する" >&2; exit 2; }
    bad_channels=$(jq -r '[.collect.channels[] | select((type == "string" and test("^[A-Za-z0-9._-]+$")) or (type == "object" and ((keys-["id","label"]|length)==0) and (.id | type == "string" and test("^[A-Za-z0-9._-]+$")) and ((has("label")|not) or (.label|type=="string"))) | not)] | length' <<<"$merged")
    [ "$bad_channels" = "0" ] \
      || { echo "[error] collect.channels の各要素はチャンネルIDまたは id を持つobject" >&2; exit 2; }
    channel_dupes=$(jq -r '[.collect.channels[] | if type=="string" then . else .id end] | group_by(.) | map(select(length>1)|.[0]) | join(", ")' <<<"$merged")
    [ -z "$channel_dupes" ] || { echo "[error] collect.channels が重複: $channel_dupes" >&2; exit 2; }
    ;;
  *) echo "[error] collect.channels は all またはチャンネル配列" >&2; exit 2 ;;
esac

jq -e '.collect.targets.channel_messages | type == "boolean"' >/dev/null <<<"$merged" \
  || { echo "[error] collect.targets.channel_messages はboolean" >&2; exit 2; }
jq -e '.collect.targets.direct_mentions | type == "boolean"' >/dev/null <<<"$merged" \
  || { echo "[error] collect.targets.direct_mentions はboolean" >&2; exit 2; }
jq -e '.collect.targets.group_mentions | type == "boolean"' >/dev/null <<<"$merged" \
  || { echo "[error] collect.targets.group_mentions はboolean" >&2; exit 2; }
jq -e '.collect.targets.authored_threads | type == "boolean"' >/dev/null <<<"$merged" \
  || { echo "[error] collect.targets.authored_threads はboolean" >&2; exit 2; }
jq -e '.collect.groups | type == "array"' >/dev/null <<<"$merged" \
  || { echo "[error] collect.groups はarray" >&2; exit 2; }
jq -e '(.collect.groups | all(.[]; type == "object" and (.id | type == "string" and length > 0)))' >/dev/null <<<"$merged" \
  || { echo "[error] collect.groups の各要素は id を持つobject" >&2; exit 2; }
jq -e '(.collect.groups | all(.[]; .id|test("^[A-Za-z0-9._-]+$"))) and ([.collect.groups[].id]|length==(unique|length))' >/dev/null <<<"$merged" \
  || { echo "[error] collect.groups のidが不正または重複" >&2; exit 2; }
jq -e '(.collect.targets.group_mentions == false) or (.collect.groups | length > 0)' >/dev/null <<<"$merged" \
  || { echo "[error] group_mentions: true では collect.groups を1件以上明示する" >&2; exit 2; }

slack_dir=$(jq -r '.slack_dir' <<<"$merged")
slack_dir="${slack_dir/#\~/$HOME}"
case "$slack_dir" in
  /*) ;;
  *) slack_dir="${root}/${slack_dir}" ;;
esac

merged=$(jq -c --arg d "$slack_dir" --arg root "$root" --arg plugin "$PLUGIN_ROOT" '
  . as $cfg |
  def scopes:
    if $cfg.collect.channels == "all" then [{suffix:"all", filter:""}]
    else [$cfg.collect.channels[] | (if type == "string" then . else .id end) as $id |
      {suffix:$id, filter:(" in:<#" + $id + ">")}] end;
  ([
    (if $cfg.collect.targets.direct_mentions then scopes[] |
      {id:("search-direct-mentions-"+.suffix), tool:"slack_search_public_and_private",
       arguments:{query:("to:<@{authenticated_user_id}> on:{target_date}"+.filter)},
       provides:[("direct_thread_refs_"+.suffix)], matched:"mention_direct"} else empty end),
    (if $cfg.collect.targets.authored_threads then scopes[] |
      {id:("search-authored-threads-"+.suffix), tool:"slack_search_public_and_private",
       arguments:{query:("from:<@{authenticated_user_id}> on:{target_date}"+.filter)},
       provides:[("authored_thread_refs_"+.suffix)], matched:"authored_by_me"} else empty end),
    (if $cfg.collect.targets.group_mentions then $cfg.collect.groups[] as $g | scopes[] |
      {id:("search-group-mention-"+$g.id+"-"+.suffix), tool:"slack_search_public_and_private",
       arguments:{query:("\"<!subteam^"+$g.id+">\" on:{target_date}"+.filter)},
       provides:[("group_thread_refs_"+$g.id+"_"+.suffix)], matched:"mention_group"} else empty end)
  ]) as $search_ops |
  .slack_dir = $d | .repo_root = $root | .plugin_root = $plugin |
  .collection_plan = {
    version: 2,
    runtime_variables:{target_date:"{target_date}",target_start_ts:"{target_start_ts}",target_end_ts:"{target_end_ts}",authenticated_user_id:"{authenticated_user_id}"},
    operations:(
      [{id:"compute-target-range",script:"scripts/date-range.py",arguments:{date:"{target_date}",timezone:$cfg.timezone},provides:["target_start_ts","target_end_ts"]}] +
      (if ($search_ops|length)>0 then [{id:"resolve-authenticated-user",tool:"slack_read_user_profile",arguments:{},provides:["authenticated_user_id"]}] else [] end) +
      $search_ops +
      (if ($search_ops|length)>0 then [{id:"merge-thread-refs",script:"scripts/merge-thread-refs.py",arguments:{input:[$search_ops[] | (.matched+"={result_file:"+.id+"}")]},inputs:[$search_ops[].provides[]],dedupe_by:["channel_id","thread_ts"],merge_field:"matched",provides:["merged_thread_refs"]},{id:"read-matched-threads",tool:"slack_read_thread",foreach:"merge-thread-refs.merged_thread_refs",arguments:{channel_id:"{item.channel_id}",message_ts:"{item.thread_ts}"},bucket_template:"thread-{item.channel_id}-{item.thread_ts_digits}",provides:["thread_messages"]}] else [] end) +
      (if $cfg.collect.targets.channel_messages then [$cfg.collect.channels[] | (if type=="string" then . else .id end) as $id | {id:("read-channel-"+$id),tool:"slack_read_channel",arguments:{channel_id:$id,oldest:"{target_start_ts}",latest:"{target_end_ts}"},bucket:$id,provides:[("channel_messages_"+$id)]}] else [] end)
    )
  }
' <<<"$merged")

if [ "$explain" = "1" ]; then
  echo "# チャンネル範囲: $(jq -c '.collect.channels' <<<"$merged")" >&2
  echo "# 有効な対象: $(jq -c '[.collect.targets | to_entries[] | select(.value) | .key]' <<<"$merged")" >&2
  echo "# MCP実行計画: $(jq -c '[.collection_plan.operations[].id]' <<<"$merged")" >&2
fi
out="$merged"
