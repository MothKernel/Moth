import json
import os
import sys
import threading
from pathlib import Path
import pytest
from moth import tools, adapters


def executable(path, content="placeholder"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.mark.parametrize("tool", ["nuclei", "katana", "dnsx", "subfinder", "sslyze", "wafw00f"])
def test_system_tools_are_used_before_managed_copies(monkeypatch, tmp_path, tool):
    binary = executable(tmp_path / (tool + tools.EXE))
    managed = tmp_path / "managed"
    monkeypatch.setattr(tools, "TOOLS", managed)
    if tool in tools.PD:
        executable(managed / tool / (tool + tools.EXE))
    else:
        executable(tools.python_bin(managed / tool / "venv"))
        (managed / tool / "ready.json").write_text("{}")
    monkeypatch.setenv("PATH", str(tmp_path))
    detected = tools.command(tool)
    assert len(detected) == 1
    assert Path(detected[0]) == binary


def test_user_go_bin_detected_without_shell_path(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    binary = executable(tmp_path / "go/bin" / ("nuclei" + tools.EXE))
    assert tools.command("nuclei") == [str(binary)]


def test_python_httpx_is_not_accepted_as_projectdiscovery():
    path = Path(sys.executable)
    stat = path.stat()
    assert not tools._is_pd_httpx(str(path), stat.st_mtime_ns, stat.st_size)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable fixture")
def test_real_projectdiscovery_fingerprint(monkeypatch, tmp_path):
    binary = executable(tmp_path / "httpx", "#!/bin/sh\nprintf '%s\\n' '-status-code' '-tech-detect'\n")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert tools.command("httpx") == [str(binary)]


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable fixture")
def test_wrong_httpx_falls_back_to_managed_copy(monkeypatch, tmp_path):
    executable(tmp_path / "bin/httpx", "#!/bin/sh\nprintf '%s\\n' 'Python HTTPX client'\n")
    managed = executable(tmp_path / "managed/httpx/httpx")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(tools, "TOOLS", tmp_path / "managed")
    assert tools.command("httpx") == [str(managed)]


def test_native_zap_is_ready_without_docker(monkeypatch, tmp_path):
    native = str(tmp_path / "zap.sh")
    monkeypatch.setattr(tools, "native_zap_command", lambda: [native])
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    zap = next(row for row in tools.catalog() if row["id"] == "zap")
    assert zap["status"] == "ready"
    assert zap["source"] == "system"
    assert zap["location"] == native


def test_available_tool_does_not_trigger_reinstallation(monkeypatch):
    monkeypatch.setattr(tools, "command", lambda tool: ["existing-tool"])
    monkeypatch.setattr(tools.threading, "Thread", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected installation")))
    tools.start_install("nuclei")


def test_native_zap_adapter_passes_plan_without_docker(monkeypatch, tmp_path):
    monkeypatch.setattr(adapters, "command", lambda tool: ["native-zap"])
    monkeypatch.setattr(adapters, "resolve", lambda *args: ["203.0.113.1"])
    from moth import zap_runtime
    def run_zap(cmd,url,directory,plan,cancel,progress=None):
        assert cmd == ["native-zap"]
        assert plan["jobs"][-1]["parameters"]["reportDir"] == str(directory)
        (directory / "result.json").write_text(json.dumps({"site": [{"alerts": [{"name": "Policy absent", "riskcode": "1"}]}]}))
    monkeypatch.setattr(zap_runtime, "run", run_zap)
    monkeypatch.setattr(adapters.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Docker must not be used")))
    found = adapters.run_tool("zap", "https://example.com/", tmp_path / "zap", threading.Event())
    assert found and found[0]["tool"] == "zap"


@pytest.mark.parametrize('entry', ['bin/retire', './lib/cli.js'])
def test_retire_uses_npm_declared_entry_point(monkeypatch, tmp_path, entry):
    monkeypatch.setattr(tools, 'TOOLS', tmp_path)
    monkeypatch.setattr(tools, 'node_command', lambda: ['node'])
    monkeypatch.setattr(tools, 'executable_candidates', lambda *args: iter(()))
    package = tmp_path / 'retire/node_modules/retire'
    script = executable(package / entry)
    (package / 'package.json').write_text(json.dumps({'name': 'retire', 'version': '6.1.0', 'bin': {'retire': entry}}))
    (tmp_path / 'retire/ready.json').write_text('{"version":"6.1.0"}')
    detected = tools.command('retire')
    assert detected[0] == 'node'
    assert Path(detected[1]) == script.resolve()
    row = next(row for row in tools.catalog() if row['id'] == 'retire')
    assert row['status'] == 'ready'
    assert row['source'] == 'moth'
    assert row['version'] == '6.1.0'
    assert str(script.resolve()) in row['location']


def test_retire_string_bin_and_unsafe_or_missing_entry(tmp_path):
    package = tmp_path / 'retire'
    package.mkdir()
    (package / 'package.json').write_text(json.dumps({'bin': './cli.js'}))
    assert tools.retire_entry(package) is None
    script = executable(package / 'cli.js')
    assert tools.retire_entry(package) == script.resolve()
    executable(tmp_path / 'outside.js')
    (package / 'package.json').write_text(json.dumps({'bin': {'retire': '../outside.js'}}))
    assert tools.retire_entry(package) is None


def test_ready_install_state_cannot_hide_missing_executable(monkeypatch):
    monkeypatch.setattr(tools, 'STATE', {'retire': dict(status='ready', message='Installation completed.')})
    monkeypatch.setattr(tools, 'command', lambda tool: None)
    retire = next(row for row in tools.catalog() if row['id'] == 'retire')
    assert retire['status'] == 'error'
    assert 'could not be found' in retire['message']


def test_global_npm_retire_uses_current_entry(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, 'TOOLS', tmp_path / 'managed')
    monkeypatch.setattr(tools, 'node_command', lambda: ['node'])
    monkeypatch.setattr(tools, 'executable_candidates', lambda *args: iter(()))
    monkeypatch.setenv('APPDATA', str(tmp_path / 'global'))
    package = tmp_path / 'global/npm/node_modules/retire'
    script = executable(package / 'lib/cli.js')
    (package / 'package.json').write_text(json.dumps({'name':'retire', 'bin':{'retire':'./lib/cli.js'}}))
    assert tools.command('retire') == ['node', str(script.resolve())]
