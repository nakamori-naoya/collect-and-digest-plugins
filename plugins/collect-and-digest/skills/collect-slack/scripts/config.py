#!/usr/bin/env python3
"""collect-slack の設定fileを検査して読む唯一の入口。呼び手はpathを選ばない。

  python3 scripts/config.py check --repo <repository_path>
  python3 scripts/config.py read --repo <repository_path>

設定fileは <repositoryのgit root>/.harness-plugins/collect-slack.config.yml に固定する（1層・fallback無し）。

check: schema検査だけ。exit 0、標準出力に {"status":"ok","config":"<絶対path>"}
read : schema検査後、exit 0、標準出力に {"config":"<絶対path>","values":{設定fileのtop-level keyと値をそのまま}}
失敗 : exit 2、標準出力に {"error":"<診断>","config":"<絶対path>"|null（not_a_git_repository のとき）,"reason":"policy_missing"|"schema_violation"|"not_a_git_repository"}

schemaの正式な定義は同じdirectoryの message.py の validate_config で、このtoolはそれを共有する。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
sys.path.insert(0, str(HERE))

import harness_config  # noqa: E402
import message  # noqa: E402  同じ入口のtool。validate_config だけを使う

if __name__ == "__main__":
    harness_config.main("collect-slack", "repository", message)
