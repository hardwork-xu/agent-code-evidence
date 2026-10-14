"""Monitoring failure must be visible / 监控失效必须显式出现。"""
import subprocess
import threading
from types import SimpleNamespace

import pytest
from benchmarks.external_context import runner


class ControlledProcess:
    pid = 12345
    returncode = None

    def __init__(self):
        self.stopped = threading.Event()

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9
        self.stopped.set()

    def communicate(self, *args, **kwargs):
        assert self.stopped.wait(3), 'monitor failed to stop synthetic process'
        return b'', b''


@pytest.mark.parametrize('mode', ['timeout', 'invalid', 'too_large'])
def test_monitor_failure_or_limit_stops_worker(monkeypatch, mode):
    monkeypatch.setattr(runner.platform, 'system', lambda: 'Darwin')
    process = ControlledProcess()
    monkeypatch.setattr(runner.subprocess, 'Popen', lambda *a, **k: process)
    calls = 0

    def ps(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(returncode=0, stdout='10\n')
        if mode == 'timeout':
            raise subprocess.TimeoutExpired('ps', 2)
        return SimpleNamespace(returncode=0, stdout='invalid' if mode == 'invalid' else '20\n')
    monkeypatch.setattr(runner.subprocess, 'run', ps)
    rc, _, _, state = runner.run_worker({'resources': {'max_address_space_bytes': 1024}}, 2)
    assert rc == -9
    assert state['failed'] is (mode != 'too_large')
    assert state['exceeded'] is (mode == 'too_large')


def test_monitor_preflight_failure_launches_nothing(monkeypatch):
    monkeypatch.setattr(runner.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=1, stdout=''))
    monkeypatch.setattr(runner.subprocess, 'Popen', lambda *a, **k: pytest.fail('worker launched'))
    with pytest.raises(ValueError, match='preflight'):
        runner.run_worker({}, 2)
