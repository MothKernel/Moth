import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def default_data_dir(system=None, home=None, environment=None):
    import sys
    system = system or sys.platform
    home = Path(home) if home else Path.home()
    environment = os.environ if environment is None else environment
    if environment.get('MOTH_DATA_DIR'):
        return Path(environment['MOTH_DATA_DIR']).expanduser()
    if system == 'darwin':
        legacy = home / '.local/share/Moth'
        return legacy if legacy.exists() else home / 'Library/Application Support/Moth'
    if system == 'win32':
        return Path(environment.get('LOCALAPPDATA', home / 'AppData/Local')) / 'Moth'
    return home / '.local/share/Moth'


DATA = default_data_dir().resolve()
TOOLS = DATA / "tools"
RUNS = DATA / "runs"
for directory in (DATA, TOOLS, RUNS):
    directory.mkdir(parents=True, exist_ok=True)
