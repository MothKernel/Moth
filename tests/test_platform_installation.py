import os
import pytest
from pathlib import Path
from moth.config import default_data_dir
from moth import shortcuts, tools


def test_native_data_directories_and_legacy_mac_compatibility(tmp_path):
    assert default_data_dir('darwin', tmp_path, {}) == tmp_path/'Library/Application Support/Moth'
    assert default_data_dir('linux', tmp_path, {}) == tmp_path/'.local/share/Moth'
    assert default_data_dir('win32', tmp_path, {'LOCALAPPDATA':str(tmp_path/'Local')}) == tmp_path/'Local/Moth'
    assert default_data_dir('darwin', tmp_path, {'MOTH_DATA_DIR':str(tmp_path/'custom')}) == tmp_path/'custom'
    legacy=tmp_path/'.local/share/Moth';legacy.mkdir(parents=True)
    assert default_data_dir('darwin', tmp_path, {}) == legacy


@pytest.mark.skipif(os.name == "nt", reason="POSIX macOS shortcut simulation")
def test_mac_shortcut_uses_app_bundle_and_does_not_replace_user_files(monkeypatch,tmp_path):
    import pytest
    app=tmp_path/'Applications/Moth.app'
    binary=app/'Contents/MacOS/Moth';binary.parent.mkdir(parents=True);binary.touch()
    monkeypatch.setattr(shortcuts.sys,'platform','darwin')
    monkeypatch.setattr(shortcuts.sys,'frozen',True,raising=False)
    monkeypatch.setattr(shortcuts.sys,'executable',str(binary))
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path))
    alias=Path(shortcuts.create_shortcuts())
    assert alias.is_symlink() and alias.resolve()==app
    assert shortcuts.create_shortcuts()==str(alias)
    alias.unlink();alias.mkdir()
    with pytest.raises(ValueError,match='already exists'):shortcuts.create_shortcuts()


@pytest.mark.skipif(os.name == "nt", reason="POSIX macOS launcher simulation")
def test_mac_source_launcher_quotes_spaces(monkeypatch,tmp_path):
    project=tmp_path/'Project with spaces'
    monkeypatch.setattr(shortcuts,'ROOT',project/'moth')
    monkeypatch.setattr(shortcuts.sys,'platform','darwin')
    monkeypatch.setattr(shortcuts.sys,'frozen',False,raising=False)
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path))
    launcher=Path(shortcuts.create_shortcuts())
    assert launcher.name=='Moth.command'
    assert "'"+str(project/'start.sh')+"'" in launcher.read_text()
