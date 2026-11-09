# Native desktop distribution. Build on the target OS with: pyinstaller Moth.spec
import sys
import tomllib
from pathlib import Path

root = Path(SPECPATH)
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
icon = root / ("moth/resources/moth.icns" if sys.platform == "darwin" else "moth/resources/moth.ico")
a = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)],
    datas=[(str(root / 'moth/resources'), 'moth/resources'),
           (str(root / 'moth/templates'), 'moth/templates')],
    hiddenimports=[],
    excludes=['fastapi', 'uvicorn', 'PySide6.QtWebEngineCore',
              'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
              'tkinter', 'pytest', 'playwright'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='Moth',
    console=False, debug=False, strip=False, upx=False,
    icon=str(icon),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Moth')

if sys.platform == 'darwin':
    app = BUNDLE(
        coll, name='Moth.app', icon=str(icon),
        bundle_identifier='io.github.MothKernel.Moth',
        info_plist={
            'CFBundleName': 'Moth',
            'CFBundleShortVersionString': version,
            'CFBundleVersion': version,
            'LSMinimumSystemVersion': '15.0',
            'NSHighResolutionCapable': True,
        },
    )
