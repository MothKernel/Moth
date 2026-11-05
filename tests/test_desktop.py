import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from PySide6.QtCore import QSettings, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog
from moth.desktop import MainWindow, TRANSLATIONS
from moth import storage


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    yield app


@pytest.fixture
def window(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    window.show()
    qapp.processEvents()
    yield window
    window.close()
    qapp.processEvents()


def wait_until(qapp, predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        QTest.qWait(25)
    raise AssertionError("Native UI did not reach the expected state")


def test_native_window_language_and_navigation(window, qapp):
    assert window.isVisible()
    assert window.windowTitle() == "Moth 0.2.0"
    assert window.tool_checks.keys() == {"httpx", "sslyze", "katana", "zap", "nuclei", "retire", "dnsx", "wafw00f", "subfinder", "nmap"}
    for code in ("ro", "ru", "en"):
        window.language_box.setCurrentIndex(window.language_box.findData(code))
        assert window.heading.text() == TRANSLATIONS[code]["assessment"]
        assert window.settings.value("language") == code
    QTest.mouseClick(window.nav[1], Qt.MouseButton.LeftButton)
    assert window.pages.currentIndex() == 1
    assert window.tools_layout.count() == 10
    assert window.heading.text() == "Tools"
    QTest.mouseClick(window.nav[2], Qt.MouseButton.LeftButton)
    assert window.pages.currentIndex() == 2


def test_native_scan_and_exports(window, qapp, monkeypatch, tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "session=NEVER-SAVE-THIS")
            self.end_headers()
            self.wfile.write(b"<html>Local lab</html>")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        window.target.setText(f"http://127.0.0.1:{server.server_port}")
        window.authorized.setChecked(True)
        window.lab.setChecked(True)
        QTest.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
        wait_until(qapp, lambda: window.current and window.current["status"] == "completed")
        assert window.findings.topLevelItemCount() >= 5
        assert "NEVER-SAVE-THIS" not in json.dumps(window.current)
        assert window.explanation.toPlainText()
        QTest.mouseClick(window.technical_toggle, Qt.MouseButton.LeftButton, pos=QPoint(8, window.technical_toggle.height() // 2))
        assert window.technical.isVisible()
        assert window.technical.toPlainText()
        for extension in ("html", "json"):
            destination = tmp_path / ("report." + extension)
            monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, dest=destination: (str(dest), ""))
            window.export_report(extension)
            assert destination.exists()
            assert "NEVER-SAVE-THIS" not in destination.read_text(encoding="utf-8")
        window.switch_page(2)
        assert window.history.rowCount() == 1
        window.open_history(0)
        assert window.pages.currentIndex() == 0
    finally:
        server.shutdown()
        server.server_close()


def test_permission_error_is_shown_in_window(window):
    window.target.setText("https://example.com")
    window.start_scan()
    assert window.notice.isVisible()
    assert "permission" in window.notice.text()
    assert window.current is None


def test_language_catalog_is_complete():
    assert set(TRANSLATIONS["en"]) == set(TRANSLATIONS["ro"]) == set(TRANSLATIONS["ru"])


def test_desktop_launcher_exits_after_smoke_test(tmp_path):
    import os
    import sys
    import subprocess
    from pathlib import Path
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", MOTH_DATA_DIR=str(tmp_path))
    result = subprocess.run([sys.executable, "main.py", "--smoke-test"],
                            cwd=Path(__file__).resolve().parents[1], env=env,
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
