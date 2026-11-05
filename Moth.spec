# Native desktop distribution. Build on the target OS with: pyinstaller Moth.spec
from pathlib import Path

root = Path(SPECPATH)
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
    icon=str(root / 'moth/resources/moth.ico'),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Moth')
