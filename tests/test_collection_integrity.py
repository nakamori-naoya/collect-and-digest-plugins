import contextlib
import importlib.util
import io
import json
import multiprocessing
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

slack = load('slack', 'plugins/collect-and-digest/skills/collect-slack/scripts/message.py')
meeting = load('meeting', 'plugins/collect-and-digest/skills/collect-notes/scripts/note.py')
store = slack.collection_store


def call(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return json.loads(out.getvalue())


def append(args, cfg):
    call(slack.cmd_append, args, cfg)


class CollectionIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cfg = {'slack_dir': str(self.root / 'slack'), 'notes_dir': str(self.root / 'notes'), 'timezone': 'UTC',
                    'collect': {'credential_redaction': False, 'transcript': True},
                    'collection_plan': {'operations': [{'id': 'channel', 'bucket': 'C1'}]}}

    def tearDown(self):
        self.temp.cleanup()

    def args(self, ts='1788566401.000001', text='first', **extra):
        path = self.root / (ts + '.jsonl')
        path.write_text(json.dumps({'ts': ts, 'text': text, 'permalink': 'https://slack.test/message', **extra}) + '\n')
        return SimpleNamespace(target_date='2026-09-05', operation_id='channel', bucket='C1', thread_ref='',
                               messages_file=str(path), label='test', url='', omitted='', tags='', thread_ts='', thread_permalink='')

    def test_parallel_append_retains_all_and_ledger_matches(self):
        args = [self.args(f'178856640{i}.000001') for i in range(1, 9)]
        context = multiprocessing.get_context('fork')
        processes = [context.Process(target=append, args=(arg, self.cfg)) for arg in args]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        messages = slack.parse_existing(self.root / 'slack/2026-09-05/C1.md')
        self.assertEqual(len(messages), 8)
        self.assertEqual(slack.read_index(self.cfg)[-1]['message_count'], 8)

    def test_interruption_replays_body_and_ledger_before_read(self):
        root = self.root / 'transaction'
        with store.locked(root):
            real = store.atomic_write
            def interrupt(path, content):
                if Path(path).name == 'index.jsonl':
                    raise OSError('interruption')
                real(path, content)
            with patch.object(store, 'atomic_write', side_effect=interrupt), self.assertRaises(OSError):
                store.commit(root, {root / 'body.md': 'body', root / 'index.jsonl': '{}\n'})
        with store.locked(root):
            self.assertEqual((root / 'body.md').read_text(), 'body')
            self.assertEqual((root / 'index.jsonl').read_text(), '{}\n')
            self.assertFalse((root / '.collection-pending.json').exists())

    def test_edit_and_explicit_delete_preserve_archive(self):
        args = self.args()
        call(slack.cmd_append, args, self.cfg)
        args = self.args(text='edited')
        call(slack.cmd_append, args, self.cfg)
        args = self.args(text='', deleted=True)
        call(slack.cmd_append, args, self.cfg)
        saved = slack.parse_existing(self.root / 'slack/2026-09-05/C1.md')[0]
        self.assertEqual(saved['text'], 'edited')
        self.assertTrue(saved['deleted'])
        self.assertEqual(saved['versions'][0]['text'], 'first')
        args.latest_ts = saved['ts']
        self.assertEqual(call(slack.cmd_check, args, self.cfg)['decision'], 'recheck')
        Path(args.messages_file).write_text('')
        call(slack.cmd_append, args, self.cfg)
        self.assertEqual(len(slack.parse_existing(self.root / 'slack/2026-09-05/C1.md')), 1)

    def test_metadata_update_and_date_history(self):
        body = self.root / 'body.txt'
        body.write_text('same body')
        args = SimpleNamespace(source='notion', source_id='page', target_date='2026-09-05', body_file=str(body),
                               transcript_file='', props='', url='https://notion.test', title='old', occurred_at='',
                               attendees='', recording_url='', source_updated_at='one', omitted='')
        call(meeting.cmd_write, args, self.cfg)
        args.title, args.source_updated_at, args.attendees = 'new', 'two', 'Alice,Bob'
        self.assertEqual(call(meeting.cmd_write, args, self.cfg)['decision'], 'updated')
        record = meeting.read_index(self.cfg)[-1]
        self.assertEqual(record['metadata']['attendees'], ['Alice', 'Bob'])
        self.assertIn('title: "new"', Path(record['path']).read_text())
        self.assertEqual(call(meeting.cmd_check, args, self.cfg)['decision'], 'unchanged')
        self.assertEqual(call(meeting.cmd_write, args, self.cfg)['decision'], 'unchanged')
        args.target_date = '2026-09-06'
        call(meeting.cmd_write, args, self.cfg)
        self.assertTrue(Path(record['path']).exists())
        self.assertEqual(meeting.read_index(self.cfg)[-1]['previous_path'], record['path'])

    def test_invalid_ledger_schema_refuses_read_and_write_without_data_changes(self):
        for invalid in (None, [], {}, {"source": "slack"}):
            for module, directory, action in ((slack, 'slack', 'append'), (meeting, 'notes', 'write')):
                root = self.root / directory
                root.mkdir(exist_ok=True)
                ledger = root / 'index.jsonl'
                ledger.write_text(json.dumps(invalid) + '\n')
                before = ledger.read_bytes()
                args = self.args()
                args.latest_ts = ''
                args.source, args.source_id, args.source_updated_at = 'notion', 'page', ''
                for fn in (module.cmd_check, lambda a, c: module.read_index(c)):
                    with self.assertRaises(SystemExit) as error, contextlib.redirect_stdout(io.StringIO()):
                        fn(args, self.cfg)
                    self.assertEqual(error.exception.code, 2)
                    self.assertEqual(ledger.read_bytes(), before)
                if module is meeting:
                    body = self.root / 'ledger-test-body.txt'
                    body.write_text('unchanged original')
                    args.body_file, args.transcript_file, args.props = str(body), '', ''
                    args.title, args.url, args.occurred_at = 'fixture', 'https://notion.test', ''
                    args.attendees, args.recording_url, args.omitted = '', '', ''
                with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
                    getattr(module, 'cmd_' + action)(args, self.cfg)
                self.assertEqual(ledger.read_bytes(), before)
                if not isinstance(invalid, dict):
                    with self.assertRaises(ValueError):
                        store.append_index(ledger, {'source': 'fixture'})
                    self.assertEqual(ledger.read_bytes(), before)

    def test_yaml_scalars_round_trip(self):
        for module in (slack, meeting):
            for value in ('true', 'null', '00123', '2026-09-05', 'a\nb', 'on', '', 'tab\there'):
                output = subprocess.run(['yq', '-o=json', '.'], input='value: ' + module.yaml_scalar(value), text=True, capture_output=True, check=True)
                self.assertEqual(json.loads(output.stdout)['value'], value)

    def test_guard_refuses_unavailable_timeout_and_unknown_status(self):
        for outcome in (FileNotFoundError(), subprocess.TimeoutExpired('git', 10), subprocess.CompletedProcess([], 129, '', 'bad')):
            with patch.object(store.subprocess, 'run', side_effect=outcome if isinstance(outcome, Exception) else None,
                              return_value=outcome), self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
                slack.guard_dir(str(self.root))
        allowed = subprocess.CompletedProcess([], 128, '', 'fatal: not a git repository (or any parent)')
        with patch.object(store.subprocess, 'run', return_value=allowed):
            slack.guard_dir(str(self.root))

    # 基準資料: digest READMEの「完全な設定」例と公開playbook固有validator。
    # 基準資料: 各入口の assets/*.config.example.yml と scripts の validate_config。
    # 入力: 記入例YAMLをyqでJSONへ変換したもの。合格述語: 記入例を各scriptのvalidate_configが受理する。
    # 反例: keyの追加・欠落・型違い・許容外の値を拒否する。境界例: digestの空sourcesは構造上合法（material.py listで停止）。
    # 意味評価: 設定値が利用者の収集目的に合うかは本文を読む。
    def test_config_examples_match_schema_and_reject_mutations(self):
        digest = load('digest', 'plugins/collect-and-digest/skills/digest/scripts/material.py')
        sessions = load('sessions', 'plugins/collect-and-digest/skills/collect-sessions/scripts/session.py')
        cases = [
            (slack, 'plugins/collect-and-digest/skills/collect-slack/assets/collect-slack.config.example.yml',
             [lambda c: c.__setitem__('extra', 1), lambda c: c['collect'].pop('max_bytes'),
              lambda c: c.__setitem__('instructions', {'collection': {'directive': 'x'}}),
              lambda c: c['collect']['targets'].__setitem__('direct_mentions', 'yes'),
              lambda c: (c['collect'].__setitem__('channels', 'all'), c['collect']['targets'].__setitem__('channel_messages', True)),
              lambda c: c['collect'].__setitem__('channels', []),
              lambda c: (c['collect']['targets'].__setitem__('group_mentions', True), c['collect'].__setitem__('groups', []))]),
            (meeting, 'plugins/collect-and-digest/skills/collect-notes/assets/collect-notes.config.example.yml',
             [lambda c: c.__setitem__('extra', 1), lambda c: c['collect'].pop('transcript'),
              lambda c: c['collect']['sources'].__setitem__('slack', {'enabled': True}),
              lambda c: c.__setitem__('timezone', 'Mars/Olympus')]),
            (sessions, 'plugins/collect-and-digest/skills/collect-sessions/assets/collect-sessions.config.example.yml',
             [lambda c: c.__setitem__('extra', 1), lambda c: c['collection'].pop('max_scan_files'),
              lambda c: (c['sources']['claude_code'].__setitem__('enabled', False), c['sources']['codex'].__setitem__('enabled', False)),
              lambda c: c['collection'].__setitem__('max_scan_files', 0)]),
            (digest, 'plugins/collect-and-digest/skills/digest/assets/digest.config.example.yml',
             [lambda c: c.__setitem__('steps', []), lambda c: c['digests'][0].__setitem__('type', 'tutorial'),
              lambda c: c['output'].__setitem__('format', 'html'), lambda c: c['digests'].append(dict(c['digests'][0]))]),
        ]
        for module, relative, mutations in cases:
            parsed = subprocess.run(['yq', '-o=json', '.', str(ROOT / relative)], text=True, capture_output=True, check=True)
            example = json.loads(parsed.stdout)
            module.validate_config(json.loads(json.dumps(example)), relative)
            for mutate in mutations:
                broken = json.loads(json.dumps(example))
                mutate(broken)
                with self.assertRaises(SystemExit, msg=f'{relative}: {mutate}'):
                    with contextlib.redirect_stdout(io.StringIO()):
                        module.validate_config(broken, relative)
        empty_sources = json.loads(subprocess.run(['yq', '-o=json', '.', str(ROOT / cases[3][1])], text=True, capture_output=True, check=True).stdout)
        empty_sources['sources'] = []
        digest.validate_config(empty_sources, 'boundary')

    # 基準資料: 1層の設定fileの置き場規則。入力: <repo>/.harness-plugins/<entry>.config.yml。
    # 合格述語: 相対 slack_dir / notes_dir がrepository root（設定fileの2つ上）基準の絶対pathへ解決される。
    def test_relative_dirs_resolve_against_repository_root(self):
        repo = self.root / 'repo'
        (repo / '.harness-plugins').mkdir(parents=True)
        for module, name, key in ((slack, 'collect-slack', 'slack_dir'), (meeting, 'collect-notes', 'notes_dir')):
            source = ROOT / f'plugins/collect-and-digest/skills/{name}/assets/{name}.config.example.yml'
            target = repo / '.harness-plugins' / f'{name}.config.yml'
            target.write_text(source.read_text().replace(f'{key}: ~/meeting-notes', f'{key}: notes'))
            cfg = module.load_config(str(target))
            self.assertTrue(Path(cfg[key]).is_absolute())
            self.assertEqual(Path(cfg[key]).parent, repo.resolve())
            self.assertEqual(cfg['repo_root'], str(repo.resolve()))
        self.assertEqual([op['id'] for op in slack.load_config(str(repo / '.harness-plugins/collect-slack.config.yml'))['collection_plan']['operations']][:2],
                         ['compute-target-range', 'resolve-authenticated-user'])

    # 基準資料: lib/harness_config.py の契約と各入口の validate_config。
    # 入力: `config.py check|read --repo <path>`（collect-sessions は引数なしで XDG_CONFIG_HOME）。stdinは使わない。
    # 正規化: git rev-parse --show-toplevel で git root を解決し、<root>/.harness-plugins/<entry>.config.yml を yq でJSON化する。
    # 合格述語: check は exit 0 と {"status":"ok","config":<絶対path>}、read は exit 0 と {"config","values"}（values は top-level key をそのまま）。
    #   失敗は exit 2 と {"error","config","reason"} で、reason は policy_missing / schema_violation / not_a_git_repository のどれか。not_a_git_repository では config は null。
    # 正例: 記入例を置いた git repository の sub directory から check / read。反例: file不在、top-level key の過不足、yq で読めない file、git repository でない --repo。
    # 境界例: --repo は git root の sub directory でもよい。collect-sessions は --repo を受け付けず、XDG_CONFIG_HOME を固定位置とする。
    # 意味評価: 設定値が収集目的に合うかは本文を読む。
    def test_config_tool_contract(self):
        def run(entry, *args, env=None):
            script = ROOT / f'plugins/collect-and-digest/skills/{entry}/scripts/config.py'
            merged = dict(**__import__('os').environ)
            merged.update(env or {})
            result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, env=merged)
            return result.returncode, (json.loads(result.stdout) if result.stdout.strip() else None), result.stderr

        repo = self.root / 'config-repo'
        (repo / '.harness-plugins').mkdir(parents=True)
        (repo / 'sub').mkdir()
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        for entry in ('collect-notes', 'collect-slack', 'digest'):
            example = ROOT / f'plugins/collect-and-digest/skills/{entry}/assets/{entry}.config.example.yml'
            (repo / '.harness-plugins' / f'{entry}.config.yml').write_text(example.read_text())
            expected = str((repo / '.harness-plugins' / f'{entry}.config.yml').resolve())
            code, out, _ = run(entry, 'check', '--repo', str(repo / 'sub'))
            self.assertEqual((code, out), (0, {'status': 'ok', 'config': expected}), entry)
            code, out, _ = run(entry, 'read', '--repo', str(repo))
            self.assertEqual(code, 0, entry)
            self.assertEqual(set(out), {'config', 'values'})
            self.assertEqual(out['config'], expected)
            self.assertEqual(out['values']['version'], 1)
            self.assertEqual(set(out['values']), set(json.loads(subprocess.run(['yq', '-o=json', '.', str(example)], text=True, capture_output=True, check=True).stdout)))
        nongit = self.root / 'not-a-repo'
        nongit.mkdir()
        code, out, _ = run('digest', 'check', '--repo', str(nongit))
        self.assertEqual((code, out['reason'], out['config']), (2, 'not_a_git_repository', None))
        (repo / '.harness-plugins/digest.config.yml').unlink()
        code, out, _ = run('digest', 'read', '--repo', str(repo))
        self.assertEqual((code, out['reason']), (2, 'policy_missing'))
        self.assertTrue(out['config'].endswith('/.harness-plugins/digest.config.yml'))
        (repo / '.harness-plugins/digest.config.yml').write_text('version: 1\n')
        code, out, _ = run('digest', 'check', '--repo', str(repo))
        self.assertEqual((code, out['reason']), (2, 'schema_violation'))
        self.assertIn('top-level key', out['error'])
        (repo / '.harness-plugins/digest.config.yml').write_text('a: [\n')
        code, out, _ = run('digest', 'check', '--repo', str(repo))
        self.assertEqual((code, out['reason']), (2, 'schema_violation'))
        self.assertIn('読めない', out['error'])
        code, out, err = run('digest', 'check')
        self.assertEqual((code, out), (2, None))
        self.assertIn('--repo', err)

        xdg = self.root / 'xdg'
        (xdg / 'harness-plugins').mkdir(parents=True)
        example = ROOT / 'plugins/collect-and-digest/skills/collect-sessions/assets/collect-sessions.config.example.yml'
        target = xdg / 'harness-plugins/collect-sessions.config.yml'
        target.write_text(example.read_text())
        code, out, _ = run('collect-sessions', 'check', env={'XDG_CONFIG_HOME': str(xdg)})
        self.assertEqual((code, out), (0, {'status': 'ok', 'config': str(target)}))
        code, out, _ = run('collect-sessions', 'read', env={'XDG_CONFIG_HOME': str(xdg)})
        self.assertEqual((code, out['config'], out['values']['version']), (0, str(target), 1))
        code, out, err = run('collect-sessions', 'check', '--repo', str(repo), env={'XDG_CONFIG_HOME': str(xdg)})
        self.assertEqual((code, out), (2, None))
        self.assertIn('--repo', err)
        target.write_text('version: 1\n')
        code, out, _ = run('collect-sessions', 'read', env={'XDG_CONFIG_HOME': str(xdg)})
        self.assertEqual((code, out['reason']), (2, 'schema_violation'))
        target.unlink()
        code, out, _ = run('collect-sessions', 'check', env={'XDG_CONFIG_HOME': str(xdg)})
        self.assertEqual((code, out['reason'], out['config']), (2, 'policy_missing', str(target)))

if __name__ == '__main__':
    unittest.main()
