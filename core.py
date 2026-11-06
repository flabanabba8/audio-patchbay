"""Guarded default-source changes through pactl; no existing stream rerouting."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import uuid


def pactl(*args):
    env = {k: os.environ[k] for k in ('HOME', 'XDG_RUNTIME_DIR', 'PULSE_SERVER', 'PULSE_COOKIE', 'LANG') if k in os.environ}
    env['PATH'] = os.defpath
    try:
        result = subprocess.run(['pactl', *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('pactl is unavailable or timed out') from exc
    if result.returncode:
        raise RuntimeError('Audio server command failed')
    return result.stdout.decode('utf-8')


class Patchbay:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    @contextlib.contextmanager
    def lock(self):
        with (self.root / '.lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def state_path(self, snapshot_id):
        if not isinstance(snapshot_id, str) or len(snapshot_id) != 32 or any(c not in '0123456789abcdef' for c in snapshot_id):
            raise ValueError('Invalid snapshot ID')
        path = self.root / (snapshot_id + '.json')
        if path.is_symlink():
            raise ValueError('Invalid snapshot')
        return path

    def save(self, path, state):
        temp = self.root / (uuid.uuid4().hex + '.tmp')
        try:
            temp.write_text(json.dumps(state))
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def sources(self):
        try:
            items = json.loads(pactl('-f', 'json', 'list', 'sources'))
            return [{'name': item['name'], 'description': item.get('description', ''), 'state': item.get('state', ''), 'mute': item.get('mute')} for item in items]
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError('Audio server returned invalid source information') from exc

    def current(self):
        return pactl('get-default-source').strip()

    def inspect_sources(self):
        with self.lock():
            sources, current = self.sources(), self.current()
            if current not in {item['name'] for item in sources}:
                raise RuntimeError('Default source is not in the source list')
            snapshot_id = uuid.uuid4().hex
            self.save(self.state_path(snapshot_id), {'original': current, 'selected': None})
            return {'snapshot_id': snapshot_id, 'default_source': current, 'sources': sources}

    def select_source(self, snapshot_id, source_name):
        if not isinstance(source_name, str) or not source_name or source_name.startswith('-'):
            raise ValueError('Invalid source name')
        with self.lock():
            path = self.state_path(snapshot_id)
            state = json.loads(path.read_text())
            if state['selected'] is not None:
                raise ValueError('Snapshot has already been used')
            if self.current() != state['original']:
                raise ValueError('Default source changed; inspect again')
            if source_name not in {x['name'] for x in self.sources()}:
                raise ValueError('Source is no longer available')
            state['selected'] = source_name
            self.save(path, state)
            pactl('set-default-source', source_name)
            if self.current() != source_name:
                raise RuntimeError('Could not verify selected default source; inspect audio state')
            return {'default_source': source_name, 'snapshot_id': snapshot_id}

    def restore_source(self, snapshot_id):
        with self.lock():
            path = self.state_path(snapshot_id)
            state = json.loads(path.read_text())
            if state['selected'] is None:
                raise ValueError('Snapshot has no active selection')
            current = self.current()
            if current == state['original']:
                state['selected'] = None
                self.save(path, state)
                return {'default_source': current, 'already_restored': True}
            if current != state['selected']:
                raise ValueError('Default changed independently; inspect before restoring')
            if state['original'] not in {x['name'] for x in self.sources()}:
                raise ValueError('Original source is no longer available')
            pactl('set-default-source', state['original'])
            if self.current() != state['original']:
                raise RuntimeError('Could not verify restored default source')
            state['selected'] = None
            self.save(path, state)
            return {'default_source': state['original'], 'already_restored': False}

    def list_snapshots(self):
        with self.lock():
            paths = sorted(self.root.glob('*.json'))
            if len(paths) > 1000: raise ValueError('More than 1,000 snapshot records')
            rows, unreadable = [], 0
            for path in paths:
                if len(path.stem) != 32 or any(c not in '0123456789abcdef' for c in path.stem): continue
                try:
                    if path.is_symlink(): raise ValueError('Invalid snapshot')
                    state = json.loads(path.read_text(encoding='utf-8'))
                    if not isinstance(state, dict) or 'selected' not in state or not isinstance(state.get('original'), str) or not (state['selected'] is None or isinstance(state['selected'], str)):
                        raise ValueError('Invalid snapshot state')
                    rows.append({'snapshot_id': path.stem, 'selection_recorded': state['selected'] is not None})
                except (OSError, ValueError, TypeError, AttributeError):
                    unreadable += 1
            return {'snapshots': rows, 'unreadable_records': unreadable,
                    'notice': 'Local records only; the current audio default may have changed. No audio server was contacted.'}
