"""Opt-in native UI integration check against an ephemeral local laboratory."""
import os
import sys
import time
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from moth.desktop import MainWindow
from moth import tools


class Lab(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Set-Cookie", "session=NATIVE-LAB-SECRET; Path=/")
        self.end_headers()
        self.wfile.write(b"<html><title>Moth native lab</title><h1>Local lab</h1></html>")

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Lab)
threading.Thread(target=server.serve_forever, daemon=True).start()
app = QApplication([])
app.setStyle("Fusion")
window = MainWindow(QSettings("/tmp/moth-native-verification.ini", QSettings.Format.IniFormat))
window.show()
try:
    window.target.setText(f"http://127.0.0.1:{server.server_port}")
    window.authorized.setChecked(True)
    window.lab.setChecked(True)
    selected = [tool for tool in ("httpx", "nmap") if tools.command(tool)]
    window.extra_toggle.setChecked(True)
    for tool in selected:
        window.tool_checks[tool].setChecked(True)
    QTest.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        app.processEvents()
        if window.current and window.current["status"] in ("completed", "failed", "partial"):
            break
        QTest.qWait(50)
    assert window.current and window.current["status"] == "completed", window.current
    assert all(any(f["tool"] == tool for f in window.current["findings"]) for tool in selected)
    assert "NATIVE-LAB-SECRET" not in str(window.current)
    window.grab().save("/tmp/moth-desktop-results.png")
    print("PASS: native desktop window, real local assessment, built-in checks, " + ", ".join(selected) + ", and cookie redaction")
finally:
    window.close()
    server.shutdown()
    server.server_close()
