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


def test_update_offer_requires_click_and_uses_queue(window, monkeypatch):
    from moth import tools, updates
    rows = [dict(row) for row in window.tool_rows]
    row = next(row for row in rows if row['id'] == 'httpx')
    row.update(status='ready', source='moth', version='v1.0.0', update_status='available',
               installed_version='v1.0.0', latest_version='v1.1.0')
    monkeypatch.setattr(tools, 'catalog', lambda: rows)
    calls = []
    monkeypatch.setattr(tools, 'start_install', lambda tool, update=False: calls.append((tool, update)))
    window.refresh_tools(force=True)
    from PySide6.QtWidgets import QPushButton, QLabel
    button = window.findChild(QPushButton, 'update_httpx')
    assert button.text() == 'Update'
    assert button.isEnabled()
    assert any('v1.0.0' in label.text() and 'v1.1.0' in label.text() for label in window.findChildren(QLabel))
    assert calls == []
    button.click()
    assert calls == [('httpx', True)]
    checks = []
    monkeypatch.setattr(updates, 'request_check', lambda data, force=False: checks.append(force))
    window.check_updates(force=True)
    assert checks == [True]


def test_checkbox_rows_accept_mouse_and_keyboard_and_open_tools(window, qapp, monkeypatch):
    from moth import tools
    rows = [dict(row) for row in window.tool_rows]
    for row in rows:
        if row['id'] == 'httpx':
            row['status'] = 'ready'
    monkeypatch.setattr(tools, 'catalog', lambda: rows)
    window.refresh_tools(force=True)
    for theme in ('dark', 'light'):
        window.theme_box.setCurrentIndex(window.theme_box.findData(theme))
        qapp.processEvents()
        for box in (window.authorized, window.lab, window.extra_toggle):
            box.setChecked(False)
            # The former native checkbox ignored clicks in this trailing area.
            QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(box.width()-8, box.height()//2))
            assert box.isChecked()
        assert window.options_scroll.isVisible()
        check = window.tool_checks['httpx']
        check.setChecked(False)
        QTest.mouseClick(check, Qt.MouseButton.LeftButton)
        assert check.isChecked()
        check.setFocus()
        QTest.keyClick(check, Qt.Key.Key_Space)
        assert not check.isChecked()
        QTest.mouseClick(window.extra_toggle, Qt.MouseButton.LeftButton)
        assert not window.options_scroll.isVisible()


def test_results_filters_evidence_error_help_and_coverage(window, qapp):
    from moth.adapters import observation
    from moth.findings import finding
    import datetime
    window.current = dict(id='presentation-test', target='http://127.0.0.1:3000/', created=datetime.datetime.now().isoformat(), status='partial', progress=100, stage='finished',
        tools=['httpx', 'katana', 'sslyze'], steps=[dict(tool=tool, status='failed' if tool=='sslyze' else 'completed') for tool in ('moth','httpx','katana','sslyze')],
        errors=[dict(tool='sslyze', message='Select an HTTPS URL for SSLyze.')], coverage={'http_status':200},
        findings=[finding('http','http://127.0.0.1:3000/','URL scheme: http','medium'),
                  observation('httpx','http://127.0.0.1:3000/','Web service observed','{"status_code":200,"tech":["Express"]}'),
                  observation('katana','http://127.0.0.1:3000/','Pages discovered','http://127.0.0.1:3000/account'),
                  observation('nmap','http://127.0.0.1:3000/','Web port observed','TCP 3000: open')])
    window.render_scan()
    qapp.processEvents()
    assert window.result_tabs.tabText(1) == 'Errors (1)'
    assert window.result_tabs.tabText(2) == 'Checks & coverage (4)'
    assert window.review_errors.isVisible()
    assert 'deselect SSLyze' in window.error_details.toPlainText()
    assert 'Select an HTTPS URL for SSLyze.' in window.error_details.toPlainText()
    assert window.check_list.topLevelItemCount()==4
    assert 'Http status: 200' in window.coverage_details.toPlainText()
    window.findings.setCurrentItem(window.findings.topLevelItem(1))
    assert 'Express' in window.explanation.toPlainText()
    assert 'What Moth observed' in window.explanation.toPlainText()
    window.finding_search.setText('katana')
    assert window.findings.topLevelItem(0).isHidden()
    assert not window.findings.topLevelItem(2).isHidden()
    assert 'http://127.0.0.1:3000/account' in window.explanation.toPlainText()
    window.finding_search.setText('no-such-result')
    assert window.result_title.text()=='No findings match these filters.'
    assert not window.explanation.toPlainText()
    window.finding_search.clear()
    window.severity_filter.setCurrentIndex(window.severity_filter.findData('medium'))
    assert not window.findings.topLevelItem(0).isHidden()
    assert window.findings.topLevelItem(1).isHidden()
    window.severity_filter.setCurrentIndex(0)
    window.theme_box.setCurrentIndex(window.theme_box.findData('dark'))
    # The fourth row used to get a white background from the native palette.
    window.findings.setCurrentItem(window.findings.topLevelItem(0))
    window.findings.clearFocus()
    qapp.processEvents()
    rect = window.findings.visualItemRect(window.findings.topLevelItem(3))
    pixel = window.findings.viewport().grab().toImage().pixelColor(5, rect.center().y())
    assert max(pixel.red(),pixel.green(),pixel.blue()) < 110
    window.review_errors.click()
    assert window.result_tabs.currentIndex()==1
    window.language_box.setCurrentIndex(window.language_box.findData('ro'))
    assert window.result_tabs.tabText(1)=='Erori (1)'
    assert 'debifează SSLyze' in window.error_details.toPlainText()
