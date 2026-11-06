import os
import tempfile

_data = tempfile.TemporaryDirectory(prefix="moth-tests-")
os.environ["MOTH_DATA_DIR"] = _data.name
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MOTH_DISABLE_UPDATE_CHECKS"] = "1"

import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    from moth import storage
    monkeypatch.setattr(storage, "DATA", tmp_path)
