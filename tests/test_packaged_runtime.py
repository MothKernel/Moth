import sys
from moth import tools
from moth.processes import external_environment


def test_frozen_app_never_uses_itself_as_python(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(tools.shutil, "which", lambda name: sys.executable)
    assert tools.python_runtime() is None


def test_source_app_uses_its_python_runtime():
    assert tools.python_runtime() == [sys.executable]


def test_external_scanners_do_not_inherit_packaged_libraries(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundle/libs")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/system/custom")
    monkeypatch.setenv("LIBPATH", "/bundle/libs")
    monkeypatch.delenv("LIBPATH_ORIG", raising=False)
    environment = external_environment()
    assert environment["LD_LIBRARY_PATH"] == "/system/custom"
    assert "LIBPATH" not in environment


def test_finder_launched_scanners_can_resolve_homebrew_dependencies(monkeypatch):
    import os
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setenv('PATH', os.pathsep.join(['/usr/bin', '/bin']))
    paths = external_environment()['PATH'].split(os.pathsep)
    assert paths[:2] == ['/usr/bin', '/bin']
    assert all(path in paths for path in ('/opt/homebrew/bin', '/usr/local/bin', '/opt/local/bin'))
    assert os.environ['PATH'] == os.pathsep.join(['/usr/bin', '/bin'])


def test_versioned_homebrew_python_is_detected_after_install(monkeypatch):
    from pathlib import Path
    import subprocess
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'platform','darwin')
    monkeypatch.setattr(tools.shutil,'which',lambda name:None)
    monkeypatch.setattr(Path,'is_file',lambda path:path.as_posix()=='/opt/homebrew/bin/python3.13')
    monkeypatch.setattr(tools.subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess(args,0))
    assert tools.python_runtime()==['/opt/homebrew/bin/python3.13']
