import threading
from collections import deque
import pytest
from moth import tools, updates


def row(version='v1.9.0', source='moth'):
    return dict(id='httpx', source=source, version=version, status='ready', location='/tools/httpx')


@pytest.mark.parametrize('installed,latest,status', [
    ('v1.9.0', 'v1.10.0', 'available'),
    ('1.10', 'v1.10.0', 'current'),
    ('2.0.0', 'v1.10.0', 'current'),
])
def test_numeric_version_comparison(monkeypatch, installed, latest, status):
    monkeypatch.setattr(updates, 'latest_version', lambda tool: latest)
    assert updates.check(row(installed))['update_status'] == status


@pytest.mark.parametrize('version', ['unknown', 'v2.0.0-dev', 'v2.0.0rc1', 'v1.0.0-beta'])
def test_unknown_or_prerelease_version_is_not_claimed_current(monkeypatch, version):
    monkeypatch.setattr(updates, 'latest_version', lambda tool: 'v2.0.0')
    with pytest.raises(ValueError, match='compared'):
        updates.check(row(version))


def test_docker_update_compares_pinned_digests(monkeypatch):
    installed = 'ghcr.io/zaproxy/zaproxy@sha256:' + 'a' * 64
    latest = 'ghcr.io/zaproxy/zaproxy@sha256:' + 'b' * 64
    monkeypatch.setattr(updates, 'latest_zap_digest', lambda: latest)
    data = row(installed, 'docker')
    data['id'] = 'zap'
    assert updates.check(data)['update_status'] == 'available'
    data['version'] = latest
    assert updates.check(data)['update_status'] == 'current'


def test_check_is_background_throttled_and_errors_are_visible(monkeypatch):
    for key, value in dict(RESULTS={}, WORKER=None, LAST_CHECK=0, LAST_SIGNATURE=None).items():
        monkeypatch.setattr(updates, key, value)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def check(data):
        calls.append(data['id'])
        entered.set()
        assert release.wait(5)
        raise OSError('offline')
    monkeypatch.setattr(updates, 'check', check)
    updates.request_check([row()])
    worker = updates.WORKER
    try:
        assert entered.wait(5)
        assert updates.snapshot()['httpx']['update_status'] == 'checking'
        updates.request_check([row()], force=True)
        assert calls == ['httpx']
    finally:
        release.set()
        worker.join(5)
    assert updates.snapshot()['httpx']['update_status'] == 'error'
    assert updates.snapshot()['httpx']['update_error'] == 'offline'
    updates.request_check([row()])
    assert calls == ['httpx']
    assert updates.WORKER is None
    updates.request_check([row()], force=True)
    worker = updates.WORKER
    if worker:
        worker.join(5)
    assert calls == ['httpx', 'httpx']


def test_existing_managed_tool_is_actually_upgraded(monkeypatch, tmp_path):
    for key, value in dict(STATE={}, INSTALL_QUEUE=deque(), INSTALL_WORKER=None).items():
        monkeypatch.setattr(tools, key, value)
    monkeypatch.setattr(tools, 'TOOLS', tmp_path)
    monkeypatch.setattr(tools, 'command', lambda tool: [str(tmp_path / tool / tool)])
    monkeypatch.setattr(updates, 'RESULTS', {})
    entered, release = threading.Event(), threading.Event()
    calls = []
    def install(tool):
        calls.append(tool)
        entered.set()
        assert release.wait(5)
        with tools.LOCK:
            tools.STATE[tool] = dict(status='ready', message='')
    monkeypatch.setattr(tools, 'install', install)
    tools.start_install('httpx', update=True)
    worker = tools.INSTALL_WORKER
    try:
        assert entered.wait(5)
        tools.start_install('httpx', update=True)
        tools.start_install('katana', update=True)
        assert list(tools.INSTALL_QUEUE) == ['katana']
    finally:
        release.set()
        worker.join(5)
    assert calls == ['httpx', 'katana']
    assert not worker.is_alive()


def test_update_does_not_modify_system_installation(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, 'TOOLS', tmp_path / 'managed')
    monkeypatch.setattr(tools, 'command', lambda tool: [str(tmp_path / 'system' / tool)])
    with pytest.raises(ValueError, match='package manager'):
        tools.start_install('httpx', update=True)


def test_python_venv_symlink_is_still_managed(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, 'TOOLS', tmp_path)
    executable = tmp_path / 'sslyze/venv/bin/python'
    executable.parent.mkdir(parents=True)
    import sys
    try:
        executable.symlink_to(sys.executable)
    except OSError:
        pytest.skip('Symlinks unavailable')
    assert tools.installation_source('sslyze', [str(executable), '-m', 'sslyze']) == 'moth'


def test_python_installer_uses_upgrade(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, 'TOOLS', tmp_path)
    monkeypatch.setattr(tools, 'STATE', {})
    python = tools.python_bin(tmp_path / 'sslyze/venv')
    python.parent.mkdir(parents=True)
    python.touch()
    calls = []
    monkeypatch.setattr(tools, 'run_install', lambda args: calls.append(args))
    monkeypatch.setattr(tools.subprocess, 'check_output', lambda *args, **kwargs: '6.3.1')
    tools.install('sslyze')
    assert '--upgrade' in calls[0]
    assert tools.STATE['sslyze']['status'] == 'ready'


def test_system_cli_version_reads_stderr_and_strips_ansi(monkeypatch):
    from moth import adapters
    monkeypatch.setattr(tools, 'command', lambda tool: ['/system/httpx'])
    def execute(args, directory, *rest, **kwargs):
        assert args == ['/system/httpx', '-version']
        (directory / 'stderr.log').write_text('\x1b[32m[INF] Current Version: v1.12.0\x1b[0m')
        return ''
    monkeypatch.setattr(adapters, 'execute', execute)
    assert updates.installed_version(row('', 'system')) == '1.12.0'


def test_updating_selected_tool_prevents_assessment(monkeypatch):
    from moth import engine
    monkeypatch.setattr(engine, 'catalog', lambda: [dict(id='httpx', status='queued')])
    with pytest.raises(ValueError, match='finish installing or updating'):
        engine.start('https://example.com', ['httpx'], True)
