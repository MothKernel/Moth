"""Desktop integration for source and packaged applications."""
import os
import subprocess
import sys
import shlex
from pathlib import Path
from .config import ROOT
from .processes import external_environment, no_console_flags


def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


def create_shortcuts():
    frozen = getattr(sys, "frozen", False)
    project = ROOT.parent
    binary = project / "dist/Moth" / ("Moth.exe" if os.name == "nt" else "Moth")
    if frozen:
        executable = Path(sys.executable)
        arguments = []
    elif binary.exists():
        executable = binary
        arguments = []
    else:
        executable = Path(sys.executable)
        if os.name == "nt" and executable.with_name("pythonw.exe").exists():
            executable = executable.with_name("pythonw.exe")
        arguments = [str(project / "main.py")]
    if os.name == "nt":
        env = external_environment()
        env.update(MOTH_EXECUTABLE=str(executable), MOTH_ARGUMENTS=subprocess.list2cmdline(arguments),
                   MOTH_ICON=str(ROOT / "resources/moth.ico"), MOTH_WORKDIR=str(executable.parent if frozen else project))
        script = r"""
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Moth.lnk'))
$link.TargetPath = $env:MOTH_EXECUTABLE
$link.Arguments = $env:MOTH_ARGUMENTS
$link.WorkingDirectory = $env:MOTH_WORKDIR
$link.IconLocation = $env:MOTH_ICON + ',0'
$link.Save()
"""
        subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, check=True, timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=no_console_flags())
        return "Moth.lnk"
    if sys.platform == 'darwin':
        desktop = Path.home() / 'Desktop'
        desktop.mkdir(parents=True, exist_ok=True)
        bundle = next((parent for parent in Path(sys.executable).parents if parent.suffix == '.app'), None) if frozen else project / 'dist/Moth.app'
        if bundle and bundle.is_dir():
            alias = desktop / 'Moth.app'
            if alias.is_symlink() and alias.resolve() == bundle.resolve():
                return str(alias)
            if alias.exists() or alias.is_symlink():
                raise ValueError('A different Moth.app already exists on the Desktop. Move it before creating a shortcut.')
            alias.symlink_to(bundle, target_is_directory=True)
            return str(alias)
        launcher = desktop / 'Moth.command'
        if launcher.exists():
            raise ValueError('Moth.command already exists on the Desktop. Move it before creating another launcher.')
        launcher.write_text('#!/bin/bash\nexec /bin/bash ' + shlex.quote(str(project / 'start.sh')) + '\n', encoding='utf-8')
        launcher.chmod(0o755)
        return str(launcher)
    entry = "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=Moth", "Comment=Desktop website security assessment",
        "Exec=" + " ".join(desktop_quote(arg) for arg in [str(executable)] + arguments),
        f"Path={executable.parent if frozen else project}", f"Icon={ROOT / 'resources/moth.png'}",
        "Terminal=false", "Categories=Development;Security;", "StartupNotify=true", "StartupWMClass=moth", "",
    ])
    desktop = Path.home() / "Desktop"
    for folder, name in ((Path.home() / ".local/share/applications", "moth.desktop"), (desktop, "Moth.desktop")):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text(entry, encoding="utf-8")
        path.chmod(0o755)
    return str(desktop / "Moth.desktop")
