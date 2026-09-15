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

slack = load('slack', 'plugins/skills/collection/slack-collect/scripts/message.py')
meeting = load('meeting', 'plugins/skills/collection/meeting-collect/scripts/note.py')
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

    # 正本: digest READMEの「完全な設定」例と公開playbook固有validator。
    # 入力: READMEの「設定」直後にある最初のyaml code block。
    # 正規化: code blockをUTF-8のYAMLとしてyqでJSONへ変換する。
    # 合格述語: 掲載例をvalidate-config.shが受理する。
    # 診断: validatorの既存schema診断をそのまま返す。
    # 正例: inputsと4工程を持つ掲載例。反例: inputsとinterpret-requestを除いた旧3工程例。
    # 境界例: digest定義が空でも構造上は合法。意味評価: 説明と利用目的の妥当性は本文を読む。
    def test_digest_readme_complete_example_matches_validator(self):
        """README掲載例そのものを正本validatorへ渡し、古い工程例への退行も拒否する。"""
        readme = (ROOT / 'plugins/playbooks/collection/digest/README.md').read_text()
        settings = readme.split('\n## 設定\n', 1)[1]
        configuration = settings.split('```yaml', 1)[1].split('```', 1)[0]
        parsed = subprocess.run(
            ['yq', '-o=json', '.'], input=configuration, text=True, capture_output=True, check=True
        )
        example = self.root / 'digest-readme-example.json'
        example.write_text(parsed.stdout)
        validator = ROOT / 'plugins/playbooks/collection/digest/scripts/validate-config.sh'
        accepted = subprocess.run(['bash', str(validator), str(example)], text=True, capture_output=True)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

        legacy = json.loads(parsed.stdout)
        legacy.pop('inputs')
        legacy['steps'] = legacy['steps'][1:]
        rejected = self.root / 'digest-readme-legacy.json'
        rejected.write_text(json.dumps(legacy))
        result = subprocess.run(['bash', str(validator), str(rejected)], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('schema', result.stderr)


if __name__ == '__main__':
    unittest.main()
