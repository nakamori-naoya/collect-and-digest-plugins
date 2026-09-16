# セッション形式と収集契約

## 境界

収集物は非公開索引であり、会話本文の写しではない。`source_ref.path`は要約など後続処理が正本をその場で読むための参照で、stdoutや公開資料へ出さない。

Claude Codeは`sessionId`を主セッションのnative IDとし、subagentは`sessionId:agentId`で区別する。Codexは`session_meta.payload.id`をrollout固有IDとして使い、`session_id`を主キーにしない。

対象日は各行のUTC timestampを設定timezoneへ変換して判定する。directory名やmtimeから日付を推定しない。

## privacy

- source rootではsession JSONLだけを走査する。
- auth、settings、history、shell snapshotなどを読まない。
- IDは保存先固有saltによるHMACで不透明化する。
- state directoryは0700、ファイルは0600にする。
- 本文、ID、pathを成功時の報告へ出さない。

## 更新

同じsource IDのfingerprintが不変なら`unchanged`、変化したら`updated`。書き込み中の末尾不完全行は保存対象に含めず`provisional`とする。索引の壊れた行やJSONL中間の真にparse不能な行は無視せず停止する。

## 認識できないセッションファイル

「構造的に壊れている（parse不能）」と「認識できるが対象schema外」「有効なturn/timestampがまだ0件なだけの正常な空セッション」は区別する。

- **parse不能なJSONL**（`json.loads`が失敗する行）は、既存どおりスキャン全体を止める。1件でも紛れ込んだら停止するのが安全側の設計であり、これは変えない。
- **対象schema外**（例: `subagents/workflows/wf_*/journal.jsonl`のようなWorkflowツール由来の別形式で、Claude sessionId自体を持たない）は、そのファイル1件だけをスキップして走査を続ける。
- **有効な空セッション**（Claude sessionIdはあるが、top-levelのai-title/agent-name行だけでturn/timestampがまだ1件もない）も、そのファイル1件だけをスキップして走査を続ける。

後者2つは黙って消えない。`counts.unrecognized`に件数を出し、`state_dir/skipped.jsonl`へ`{source, path, reason, observed_at}`を1行1件で記録する。この診断ログは`index.jsonl`の`source_ref.path`と同じ扱いの私的state情報であり、原文pathを標準出力の成功報告（`artifact` / `counts`）へは出さない。`artifact.skipped_log`はこのログ自身の保存先pathだけを示す。
