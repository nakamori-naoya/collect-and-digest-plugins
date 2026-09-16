"""設定fileの置き場を固定し、schema検査の結果を一つの形のJSONで標準出力へ返す共通実装。

各公開入口の scripts/config.py がこれを使う。呼び手（agent）は設定fileのpathを選ばない。

  config.py check --repo <repository_path>   schema検査だけ。exit 0 / {"status":"ok","config":"<絶対path>"}
  config.py read  --repo <repository_path>   schema検査後に値を返す。exit 0 / {"config":"<絶対path>","values":{...}}

repository scope の入口は `<repositoryのgit root>/.harness-plugins/<入口>.config.yml` に固定する。
利用者 scope の入口（collect-sessions）は `--repo` を持たず、
`${XDG_CONFIG_HOME:-~/.config}/harness-plugins/<入口>.config.yml` に固定する。どちらも1層で、fallbackは無い。

失敗は exit 2 と標準出力のJSON {"error":"<診断>","config":"<絶対path>"|null,"reason":"policy_missing"|"schema_violation"|"not_a_git_repository"}。
  policy_missing        設定fileが無い（symlinkも無いものとして扱う）
  schema_violation      key過不足・型違い・許容外の値・yqで読めないfile（detailを error に含める）
  not_a_git_repository  --repo が git repository ではない（利用者scopeの入口では出ない。設定fileのpathを決められないので config は JSON の null）

`values` は設定fileのtop-level keyと値をそのまま入れる（`version` も含む）。schemaが違う入口でも出力の形は一つである。
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REASONS = ("policy_missing", "schema_violation", "not_a_git_repository")


class ConfigError(Exception):
    def __init__(self, reason, message, config=None):
        if reason not in REASONS:
            raise ValueError("unknown reason: {}".format(reason))
        super().__init__(message)
        self.reason = reason
        self.config = config


def resolve_repository_config(entry, repo):
    env = dict(os.environ, LC_ALL="C")
    try:
        result = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=10, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigError("not_a_git_repository", "git を実行できない: {}".format(exc))
    if result.returncode or not result.stdout.strip():
        raise ConfigError("not_a_git_repository", "--repo が git repository ではない: {}".format(repo))
    root = Path(result.stdout.strip()).resolve()
    return root / ".harness-plugins" / "{}.config.yml".format(entry)


def resolve_user_config(entry):
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(os.path.abspath(os.path.join(base, "harness-plugins", "{}.config.yml".format(entry))))


def read_yaml(path):
    if path.is_symlink() or not path.is_file():
        raise ConfigError("policy_missing", "設定fileが無い: {}".format(path), str(path))
    try:
        result = subprocess.run(["yq", "-o=json", "-I=0", ".", str(path)],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigError("schema_violation", "設定fileを読めない: {} ({})".format(path, exc), str(path))
    if result.returncode:
        raise ConfigError("schema_violation",
                          "設定fileを読めない: {} ({})".format(path, result.stderr.strip()), str(path))
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise ConfigError("schema_violation", "設定fileを読めない: {} ({})".format(path, exc), str(path))


def validate_with(module, cfg, path):
    """入口のtoolが持つ validate_config(cfg, path) を、その module の fail を差し替えて呼ぶ。
    fail は診断を標準出力へ書いて exit するので、ここでは例外に変えて一つの形で返す。"""
    original = module.fail

    def raise_schema_violation(message, code=2):
        raise ConfigError("schema_violation", message, str(path))

    module.fail = raise_schema_violation
    try:
        module.validate_config(cfg, str(path))
    except SystemExit as exc:
        raise ConfigError("schema_violation", "schema検査が exit {} で終わった".format(exc.code), str(path))
    finally:
        module.fail = original
    return cfg


def run(entry, scope, module, argv=None):
    """scope は "repository"（--repo 必須）か "user"（--repo 無し）。exit code を返す。"""
    parser = argparse.ArgumentParser(prog="config.py", description="{} の設定fileを検査して読む".format(entry))
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("check", "read"):
        sp = sub.add_parser(action)
        if scope == "repository":
            sp.add_argument("--repo", required=True, help="repository 配下の任意のpath（git rootを解決する）")
    args = parser.parse_args(argv)
    config_path = None
    try:
        if scope == "repository":
            path = resolve_repository_config(entry, args.repo)
        else:
            path = resolve_user_config(entry)
        config_path = str(path)
        cfg = read_yaml(path)
        validate_with(module, cfg, path)
    except ConfigError as exc:
        print(json.dumps({"error": str(exc), "config": exc.config if exc.config is not None else config_path, "reason": exc.reason},
                         ensure_ascii=False))
        return 2
    if args.action == "check":
        print(json.dumps({"status": "ok", "config": config_path}, ensure_ascii=False))
    else:
        print(json.dumps({"config": config_path, "values": cfg}, ensure_ascii=False))
    return 0


def main(entry, scope, module):
    sys.exit(run(entry, scope, module))
