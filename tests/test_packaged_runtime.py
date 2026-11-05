import sys
from moth import tools
from moth.processes import external_environment


def test_frozen_app_never_uses_itself_as_python(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
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
