#!/usr/bin/env bash
# playbook を解決して YAML で stdout へ出す。
#
#   resolve.sh [repo_root] [--explain] [--scope=<dir>]
#
# --scope が無ければ、自分の名前から scope を決める（この段取りを入口とする実行の scope）。
# あれば、それは**入口の段取りが決めた scope** なので、作り直さずそのまま下段へ流す。
# だから scope 設定は、その入口を通る実行の中でしか効かない。
#
# **正本は shared/playbook/resolve.sh。** 各 playbook はその複製を自分の scripts/ に持つ。
# インストール時にコピーされるのは playbook のディレクトリだけなので、
# リポジトリ root の共有ファイルは配布先へ届かない。lint が複製の一致を検査する。
#
# playbook が持つのは**何を、どの順で呼ぶか**だけである。
# 各工程が中で何をするかは、その skill / script の領分で、ここは知らない。
# 順番も呼ぶ相手も同梱 playbook.yml に書く。利用者は
# <repo>/.harness-plugins/<name>.config.yml で上書きできる。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PB_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

repo=""; explain=0; scope_root=""; scope_given=0
for arg in "$@"; do
  case "$arg" in
    --explain) explain=1 ;;
    --scope=*) scope_root="${arg#--scope=}"; scope_given=1 ;;
    *) [ -n "$repo" ] || repo="$arg" ;;
  esac
done
[ -n "$repo" ] || repo="$PWD"
[ -d "$repo" ] || { echo "[error] repo directory が無い: $repo" >&2; exit 2; }
root=$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null || (cd "$repo" && pwd)) || exit 2
[ -n "$root" ] || { echo "[error] repo root を解決できない: $repo" >&2; exit 2; }

command -v yq >/dev/null 2>&1 || { echo "[error] yq が要る" >&2; exit 2; }

base="$PB_ROOT/playbook.yml"
[ -f "$base" ] || { echo "[error] playbook.yml が無い: ${base}" >&2; exit 2; }
bundled=$(yq -o=json -I=0 '.' "$base") || { echo "[error] 同梱の playbook.yml が壊れている" >&2; exit 2; }
name=$(jq -r '.name' <<<"$bundled")
personal="${XDG_CONFIG_HOME:-$HOME/.config}/harness-plugins/${name}.config.yml"
override="$root/.harness-plugins/${name}.config.yml"
# scope は入口の段取りが決める。入れ子で呼ばれた側は、渡されたものを作り直さない。
# 作り直すと「digest 経由のとき」の設定が、途中の write-doc の scope にすり替わる。
[ -n "$scope_root" ] || scope_root="$root/.harness-plugins/scopes/${name}"
# 置いたのに効かない事故を防ぐ。scope directory があるなら、中身は
# <プラグイン名>.config.yml だけに限る。綴り違いは黙って無視せず落とす。
if [ -d "$scope_root" ]; then
  for f in "$scope_root"/*; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in
      *.config.yml) ;;
      *) echo "[error] scope設定の名前が不正: ${f}（<プラグイン名>.config.yml のみ）" >&2; exit 2 ;;
    esac
  done
fi
selected="$base"; source="bundled"
[ ! -f "$personal" ] || { selected="$personal"; source="personal"; }
[ ! -f "$override" ] || { selected="$override"; source="project"; }
# 入れ子で呼ばれたときだけ、入口が決めた scope の設定を最優先で選ぶ。
# 入口の段取り自身は通常の層で解決する（自分の scope に自分を置くのは自己参照になる）。
scope_cfg=""
[ "$scope_given" = "0" ] || scope_cfg="$scope_root/${name}.config.yml"
[ -z "$scope_cfg" ] || [ ! -f "$scope_cfg" ] || { selected="$scope_cfg"; source="scope"; }
pb=$(yq -o=json -I=0 '.' "$selected" 2>/dev/null) || { echo "[error] YAML が壊れている: $selected" >&2; exit 2; }
missing=$(jq -rn --argjson req "$bundled" --argjson got "$pb" 'def required_paths($v;$p): if ($v|type)=="object" then [$v|to_entries[]|required_paths(.value;$p+[.key])[]] else [$p] end;[$req|required_paths(.;[])[] as $p|select($got|getpath($p)==null)|$p|map(tostring)|join(".")]|join(", ")')
[ -z "$missing" ] || { echo "[error] 選択したplaybook設定が自己完結していない: ${selected}（不足: ${missing}）" >&2; exit 2; }
jq -e --arg expected "$name" --argjson bundled "$bundled" '
  .version==2 and .name==$expected and (.description|type=="string" and length>0) and
  (.instructions|type=="object" and all(.[]; type=="object" and (.directive|type=="string" and length>0))) and
  (.requires | type=="array" and length>0 and
    all(.[];
      type=="object" and
      ((keys|sort)==["marketplace","plugin"]) and
      (.plugin|type=="string" and test("^[A-Za-z0-9_-]+(?:\\.[A-Za-z0-9_-]+)*$")) and
      (.marketplace|type=="string" and test("^[A-Za-z0-9_-]+(?:\\.[A-Za-z0-9_-]+)*$"))) and
    ((map(.plugin)|length)==(map(.plugin)|unique|length))) and
  (.requires==$bundled.requires) and
  (.steps|type=="array" and length>0 and all(.[];
    type=="object" and (.id|type=="string" and test("^[A-Za-z0-9._-]+$")) and
    (.purpose|type=="string" and length>0) and
    ((.needs // [])|type=="array" and all(.[]; type=="string" and test("^[A-Za-z0-9._-]+$"))) and
    ((.provides // [])|type=="array" and all(.[]; type=="string" and test("^[A-Za-z0-9._-]+$"))) and
    ([.skill,.script,.playbook]|map(select(.!=null))|all(.[]; type=="string" and length>0)))) and
  ((keys - ($bundled|keys))|length==0)
' >/dev/null <<<"$pb" || { echo "[error] playbookのschema、name、未知キーのいずれかが不正: $selected" >&2; exit 2; }

# **同梱 playbook.yml に無いキーは、どの深さにあっても受け取らない。**
# 名前を個別に覚えることなく、廃止したキーも綴り違いもここで落ちる。
# steps などの配列の中身は利用者が並べるものなので、添字を含む経路は対象外にする。
deep_unknown=$(jq -rn --argjson req "$bundled" --argjson got "$pb" '
  [ $got | paths ]
  | map(select(all(.[]; type=="string")))
  | map(. as $p | select($req | getpath($p) == null))
  | map(join("."))
  | join(", ")')
[ -z "$deep_unknown" ] || { echo "[error] 同梱 playbook.yml に無い設定: $deep_unknown" >&2; exit 2; }

# 共通resolverは個別playbookのキーを知らない。各配布物が持つvalidatorへ委譲する。
validator="$PB_ROOT/scripts/validate-config.sh"
[ -x "$validator" ] || { echo "[error] playbook固有validatorが無い: $validator" >&2; exit 2; }
pb_file=$(mktemp "${TMPDIR:-/tmp}/${name}.playbook.XXXXXX") || exit 2
trap 'rm -f "$pb_file"' EXIT
printf '%s\n' "$pb" > "$pb_file"
bash "$validator" "$pb_file" || exit 2

n=$(jq '.steps | length' <<<"$pb")
[ "$n" -gt 0 ] || { echo "[error] steps が空: ${name}" >&2; exit 2; }
seen=""; i=0
while [ "$i" -lt "$n" ]; do
  id=$(jq -r --argjson i "$i" '.steps[$i].id // ""' <<<"$pb")
  [ -n "$id" ] || { echo "[error] steps[${i}] に id が無い" >&2; exit 2; }
  case " $seen " in *" $id "*) echo "[error] id が重複している: ${id}" >&2; exit 2 ;; esac
  seen="$seen $id"
  kinds=$(jq -r --argjson i "$i" '[.steps[$i] | (.skill//empty), (.script//empty), (.playbook//empty)] | length' <<<"$pb")
  [ "$kinds" = "1" ] || { echo "[error] steps[${i}] (${id}) は skill / script / playbook のどれか1つだけを指すこと" >&2; exit 2; }
  # needs が、前の工程の provides で満たされているか。順番の正しさを機械で見る。
  for nd in $(jq -r --argjson i "$i" '.steps[$i].needs[]?' <<<"$pb"); do
    ok=$(jq -r --argjson i "$i" --arg nd "$nd" '[.steps[:$i][] | .provides[]?] | index($nd) != null' <<<"$pb")
    [ "$ok" = "true" ] || { echo "[error] steps[${i}] (${id}) の needs「${nd}」を、前の工程が provides していない" >&2; exit 2; }
  done
  for nd in $(jq -r --argjson i "$i" '.steps[$i].conditional_needs[]?.needs[]?' <<<"$pb"); do
    ok=$(jq -r --argjson i "$i" --arg nd "$nd" '[.steps[:$i][] | .provides[]?] | index($nd) != null' <<<"$pb")
    [ "$ok" = "true" ] || { echo "[error] steps[${i}] (${id}) の conditional_needs「${nd}」を、前の工程が provides していない" >&2; exit 2; }
  done
  i=$((i + 1))
done

dependency_resolver="$PB_ROOT/scripts/resolve-dependency.py"
[ -f "$dependency_resolver" ] || { echo "[error:dependency-invalid] resolver-missing=$dependency_resolver" >&2; exit 2; }
deps='{}'
while IFS=$'\t' read -r dep market; do
  candidate=$(python3 "$dependency_resolver" --plugin-root "$PB_ROOT" \
    --plugin "$dep" --marketplace "$market") || exit 2
  deps=$(jq -c --arg k "$dep" --argjson v "$candidate" '.[$k]=$v' <<<"$deps") || exit 2
done < <(jq -r '.requires[] | [.plugin,.marketplace] | @tsv' <<<"$pb")

# requires はプラグイン名、steps[].skill はスキル名で、名前空間が違う。
# **両方を検査しないと片方だけが素通りする。** requires を通っても、steps が
# 存在しないスキルを指していれば、実行するエージェントはそれを呼べず自力で始める。
# 「規律なしで資料が出る」は、資料が出ないことより悪い。ここで止める。
available=""
while IFS=$'\t' read -r dep_root package_root manifest_path; do
  # 単一skill pluginはrootのSKILL.md、複数skill pluginだけは
  # skills/<name>/SKILL.mdを持つ。どちらも深さが決まっているので、
  # **単体配布先で広域をfindしない。**
  for sk in "$dep_root"/SKILL.md "$dep_root"/skills/*/SKILL.md; do
    [ -f "$sk" ] || continue
    sk_name=$(sed -n 's/^name: //p' "$sk" | head -1)
    [ -z "$sk_name" ] || available="$available $sk_name"
  done
  # playbook packageは複数の内部skillをmanifestで明示する。呼び出し側は
  # 内部plugin名へ依存せず、公開packageの宣言済みskillだけを利用する。
  if [ -f "$manifest_path" ]; then
    while IFS= read -r declared; do
      [ -n "$declared" ] || continue
      skill_root="$package_root/${declared#./}"
      skill_file="$skill_root/SKILL.md"
      [ -f "$skill_file" ] || continue
      sk_name=$(sed -n 's/^name: //p' "$skill_file" | head -1)
      [ -z "$sk_name" ] || available="$available $sk_name"
    done < <(jq -r '.skills | if type=="array" then .[] elif type=="string" then . else empty end' "$manifest_path")
  fi
done < <(jq -r '.[] | [.root, (.package_root // .root), .manifest] | @tsv' <<<"$deps")
# when: を持つ工程は、条件が偽なら実行されない。そのとき依存を宣言しないのは正しい。
# だから**無条件の工程だけ**を、実体があることまで確かめる対象にする。
unresolved=""
for want in $(jq -r '.steps[]? | select(.when == null) | select(.skill != null) | .skill' <<<"$pb"); do
  case " $available " in *" $want "*) ;; *) unresolved="${unresolved} ${want}" ;; esac
done
if [ -n "$unresolved" ]; then
  echo "[error] steps が指すスキルが requires のプラグインに無い:${unresolved}" >&2
  echo "        呼べないスキルを指したまま走ると、その工程だけ規律なしで進む。" >&2
  echo "        指せるスキル:${available:- （requires のプラグインにスキルが無い）}" >&2
  exit 2
fi

# script も同じ。指した先が無ければ、その工程は実行されずに飛ばされる。
# plugin: を伴うときは、その依存プラグインの配下を見る（自分の配下ではない）。
# path は配布物の中に限る。外を指せると、配られた段取りが任意の場所を実行できる。
# 区切りは空白以外にする。tab は IFS の空白文字なので、先頭の空フィールドが
# 黙って詰められ、plugin を持たない工程の path が owner 側へ入ってしまう。
while IFS='|' read -r owner rel; do
  [ -n "$rel" ] || continue
  case "$rel" in
    /*|*..*) echo "[error] steps の script は配布物内の相対pathに限る: ${rel}" >&2; exit 2 ;;
  esac
  base="$PB_ROOT"
  if [ -n "$owner" ]; then
    base=$(jq -r --arg k "$owner" '.[$k].root // ""' <<<"$deps")
    [ -n "$base" ] || { echo "[error] steps の plugin「${owner}」が requires に無い" >&2; exit 2; }
  fi
  [ -f "$base/$rel" ] \
    || { echo "[error] steps が指す script が無い: ${rel}（${base} 配下）" >&2; exit 2; }
done < <(jq -r '.steps[]? | select(.when == null) | select(.script != null)
  | ((.plugin // "") + "|" + .script)' <<<"$pb")

# 入れ子の段取りも requires を通っていること。requires に無ければ実体を探せない。
for want in $(jq -r '.steps[]? | select(.when == null) | select(.playbook != null) | .playbook' <<<"$pb"); do
  nested=$(jq -r --arg k "$want" '.[$k].root // ""' <<<"$deps")
  [ -n "$nested" ] || { echo "[error] steps が指す段取り「${want}」が requires に無い" >&2; exit 2; }
  [ -f "$nested/playbook.yml" ] && [ -x "$nested/scripts/resolve.sh" ] \
    || { echo "[error:dependency-invalid] plugin=${want} reason=playbook-entry-missing" >&2; exit 2; }
done

out=$(jq -cn --argjson pb "$pb" --argjson d "$deps" --arg root "$root" --arg pr "$PB_ROOT" \
  --arg personal "$personal" --arg project "$override" --arg scope "$scope_root" \
  '{playbook:$pb, deps:$d, repo_root:$root, playbook_root:$pr,
    instructions:($pb.instructions // {}),
    resolution:{schema:1, personal_config:$personal, project_config:$project, scope_root:$scope}}')
if [ "$explain" = "1" ]; then
  echo "# playbook: ${name}" >&2
  jq -r '.playbook.steps[] | "  \(.id): \(.skill // .script // ("playbook:" + .playbook))  — \(.purpose)"' <<<"$out" >&2
  echo "# 依存:" >&2
  jq -r '.deps | to_entries[] | "  \(.key)@\(.value.marketplace) \(.value.version) [\(.value.runtime)/\(.value.source_kind)]: \(.value.root)"' <<<"$out" >&2
  echo "# 選択した設定: ${source} (${selected})" >&2
  if [ -d "$scope_root" ]; then
    echo "# scope: ${scope_root}" >&2
    for f in "$scope_root"/*.config.yml; do [ -f "$f" ] && echo "  $f" >&2; done
  else
    echo "# scope: ${scope_root}（無し。各工程は通常の設定で解決する）" >&2
  fi
fi
printf '%s\n' "$out" | yq -P
