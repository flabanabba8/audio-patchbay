import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


def worker():
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    processes = []
    logs = (runtime / 'fixture.log').open('wb')
    try:
        for command in (['pipewire'], ['pipewire-pulse'], ['wireplumber']):
            processes.append(subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=logs, stderr=logs))
        def pactl(*args):
            return subprocess.run(['pactl', *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, check=False)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if pactl('info').returncode == 0: break
            if any(p.poll() is not None for p in processes): raise RuntimeError('Isolated audio process exited')
            time.sleep(.2)
        else: raise RuntimeError('Isolated audio server did not become ready')
        for name in ('fixture_a','fixture_b'):
            result = pactl('load-module', 'module-null-sink', 'sink_name='+name)
            if result.returncode: raise RuntimeError('Isolated null sink creation failed')
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = pactl('-f','json','list','sources')
            try: sources = json.loads(result.stdout)
            except ValueError: sources = []
            names = {item['name'] for item in sources}
            if {'fixture_a.monitor','fixture_b.monitor'} <= names: break
            time.sleep(.2)
        else: raise RuntimeError('Isolated fixture sources did not appear')
        if pactl('set-default-source','fixture_a.monitor').returncode: raise RuntimeError('Could not initialize isolated default')
        plugin = Path(__file__).resolve().parents[1] / 'core.py'
        spec = importlib.util.spec_from_file_location('patchbay_isolated_live', plugin)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        patchbay = module.Patchbay(runtime / 'plugin-state')
        state = patchbay.inspect_sources()
        if state['default_source'] != 'fixture_a.monitor': raise RuntimeError('Unexpected isolated initial default')
        patchbay.select_source(state['snapshot_id'], 'fixture_b.monitor')
        if pactl('get-default-source').stdout.strip() != b'fixture_b.monitor': raise RuntimeError('Selection not observed')
        patchbay.restore_source(state['snapshot_id'])
        if pactl('get-default-source').stdout.strip() != b'fixture_a.monitor': raise RuntimeError('Restoration not observed')
        print('Isolated PipeWire default-source selection and restoration passed')
    finally:
        for p in reversed(processes):
            if p.poll() is None: p.terminate()
        for p in reversed(processes):
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=2)
        logs.close()

@unittest.skipUnless(all(shutil.which(x) for x in ('pipewire', 'pipewire-pulse', 'wireplumber', 'pactl', 'dbus-run-session')), 'PipeWire fixture tools required')
class AudioServerTest(unittest.TestCase):
    def test_isolated_routing(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            env = {key: os.environ[key] for key in ('PATH','HOME','LANG','USER') if key in os.environ}
            env.update({'XDG_RUNTIME_DIR':tmp, 'PIPEWIRE_RUNTIME_DIR':tmp, 'PULSE_SERVER':'unix:'+str(Path(tmp)/'pulse'/'native')})
            result = subprocess.run(['dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'worker'],
                                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
            self.assertEqual(result.returncode, 0, 'Isolated audio test failed')
            print(result.stdout.decode().strip())

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'worker': worker()
    else: unittest.main()
