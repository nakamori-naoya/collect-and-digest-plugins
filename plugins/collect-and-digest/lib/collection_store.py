"""Single-writer collection transactions with redo recovery before every access."""
import fcntl
import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def guard_dir(path, fail):
    parent = Path(path).resolve()
    while not parent.is_dir():
        parent = parent.parent
    env = dict(os.environ, LC_ALL='C')
    def git(*args):
        try:
            return subprocess.run(['git', '-C', str(parent), *args], capture_output=True,
                                  text=True, timeout=10, env=env)
        except FileNotFoundError:
            fail('storage-check-unavailable: git が見つからない')
        except subprocess.TimeoutExpired:
            fail('storage-check-timeout: Git検査がタイムアウトした')
        except OSError as exc:
            fail('storage-check-unavailable: ' + str(exc))
    top = git('rev-parse', '--show-toplevel')
    if top.returncode == 128 and 'not a git repository' in top.stderr:
        return
    if top.returncode != 0:
        fail('storage-check-failed: rev-parse exit {}'.format(top.returncode))
    ignored = git('check-ignore', '-q', str(Path(path).resolve()) + os.sep)
    if ignored.returncode == 1:
        fail('storage-unprotected: 保存先がgit管理下でgitignoreされていない')
    if ignored.returncode != 0:
        fail('storage-check-failed: check-ignore exit {}'.format(ignored.returncode))


def _apply(root, writes):
    if not isinstance(writes, dict):
        raise ValueError('invalid collection transaction')
    for relative, content in writes.items():
        path = root / relative
        if not isinstance(content, str) or path.resolve().is_relative_to(root.resolve()) is False:
            raise ValueError('collection transaction escapes storage')
        atomic_write(path, content)


@contextmanager
def locked(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.collection.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        journal = root / '.collection-pending.json'
        if journal.exists():
            _apply(root, json.loads(journal.read_text()))
            journal.unlink()
        yield


def commit(root, writes):
    """Call under locked(); interrupted writes are replayed on next read/write."""
    root = Path(root)
    relative = {str(Path(path).relative_to(root)): content for path, content in writes.items()}
    journal = root / '.collection-pending.json'
    atomic_write(journal, json.dumps(relative, ensure_ascii=False))
    _apply(root, relative)
    journal.unlink()


def append_index(path, entry):
    path = Path(path)
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    for line in existing.splitlines():
        if line.strip():
            if not isinstance(json.loads(line), dict):
                raise ValueError("invalid collection ledger record: expected object")
    return existing + json.dumps(entry, ensure_ascii=False) + '\n'
