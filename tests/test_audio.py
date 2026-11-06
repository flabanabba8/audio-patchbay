import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('patchbay_core', Path(__file__).parents[1] / 'core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class AudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.current = 'mic-a'
        self.sources = [{'name': 'mic-a'}, {'name': 'mic-b'}, {'name': 'mic-c'}]
        self.plugin = core.Patchbay(Path(self.tmp.name))
        self.mock = patch.object(core, 'pactl', side_effect=self.fake)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.tmp.cleanup()

    def fake(self, *args):
        if args == ('get-default-source',): return self.current + '\n'
        if args == ('-f', 'json', 'list', 'sources'): return json.dumps(self.sources)
        if args[0] == 'set-default-source': self.current = args[1]; return ''
        raise AssertionError('Unexpected command')

    def test_recover_snapshot_without_audio_server_or_device_names(self):
        snap = self.plugin.inspect_sources()['snapshot_id']
        self.plugin.select_source(snap, 'mic-b')
        self.mock.stop()
        try:
            with patch.object(core, 'pactl', side_effect=AssertionError('Audio server must not be contacted')):
                result = self.plugin.list_snapshots()
        finally:
            self.mock.start()
        self.assertEqual(result['snapshots'], [{'snapshot_id': snap, 'selection_recorded': True}])
        (Path(self.tmp.name)/('a'*32+'.json')).write_text('{"original":"synthetic"}')
        with patch.object(core, 'pactl', side_effect=AssertionError('Audio server must not be contacted')):
            self.assertEqual(self.plugin.list_snapshots()['unreadable_records'], 1)
        self.assertNotIn('mic-a', str(result)); self.assertNotIn('mic-b', str(result))

    def test_select_and_restore(self):
        snap = self.plugin.inspect_sources()['snapshot_id']
        self.plugin.select_source(snap, 'mic-b')
        self.assertEqual(self.current, 'mic-b')
        self.plugin.restore_source(snap)
        self.assertEqual(self.current, 'mic-a')

    def test_snapshot_and_updates_are_private_under_permissive_umask(self):
        previous = os.umask(0)
        try:
            ident = self.plugin.inspect_sources()['snapshot_id']
            path = self.plugin.state_path(ident)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.plugin.select_source(ident, 'mic-b')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        finally:
            os.umask(previous)

    def test_independent_change_is_not_overwritten(self):
        snap = self.plugin.inspect_sources()['snapshot_id']
        self.plugin.select_source(snap, 'mic-b')
        self.current = 'mic-c'
        with self.assertRaisesRegex(ValueError, 'independently'):
            self.plugin.restore_source(snap)
        self.assertEqual(self.current, 'mic-c')

    def test_stale_snapshot(self):
        snap = self.plugin.inspect_sources()['snapshot_id']
        self.current = 'mic-c'
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.plugin.select_source(snap, 'mic-b')

if __name__ == '__main__':
    unittest.main()
