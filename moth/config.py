import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("MOTH_DATA_DIR", str(
    Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "Moth"
))).resolve()
TOOLS = DATA / "tools"
RUNS = DATA / "runs"
for directory in (DATA, TOOLS, RUNS):
    directory.mkdir(parents=True, exist_ok=True)
