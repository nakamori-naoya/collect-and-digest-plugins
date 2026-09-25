# セッション形式と収集契約

## 境界

収集物は非公開索引であり、会話本文の写しではない。`source_ref.path`は要約など後続処理が参照元をその場で読むための参照で、stdoutや公開資料へ出さない。

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

## 飛ばしたfileの記録

飛ばしたfileは `state_dir/skipped.jsonl` へ `{source, path, reason, observed_at}` を1行1件で記録する。このログは索引の `source_ref.path` と同じく私的な記録なので、原文のpathを成功の報告（`artifact` / `counts`）へ出さない。`artifact.skipped_log` が示すのはこのログ自身の置き場だけである。
