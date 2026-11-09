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


@pytest.mark.parametrize("saved, expected", [(None, "dark"), ("invalid", "dark"), ("light", "light"), ("dark", "dark")])
def test_theme_default_and_saved_preference(qapp, tmp_path, saved, expected):
    settings = QSettings(str(tmp_path / "theme.ini"), QSettings.Format.IniFormat)
    if saved is not None:
        settings.setValue("theme", saved)
    window = MainWindow(settings)
    try:
        assert window.theme == expected
        assert window.theme_box.currentData() == expected
        selected = "light" if expected == "dark" else "dark"
        window.theme_box.setCurrentIndex(window.theme_box.findData(selected))
        assert settings.value("theme") == selected
    finally:
        window.close()


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
        assert window.current["steps"][0]["completion_order"] == 0
        assert window.current["steps"][0]["started"] <= window.current["steps"][0]["finished"]
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


def test_combined_result_filters_sort_reset_and_selection(window):
    from moth.findings import finding
    findings=[finding('csp','https://example.com','CSP absent','low','hardening','', 'moth'),
              finding('alert','https://example.com','Rule matched','high','review','', 'nuclei'),
              finding('http','https://example.com','HTTP','medium','configuration','', 'moth'),
              finding('inventory','https://example.com','Server','info','information','', 'httpx')]
    window.current=dict(id='filters',target='https://example.com',status='completed',progress=100,stage='finished',
        tools=['httpx','nuclei'],steps=[dict(tool='moth',status='completed',completion_order=0),dict(tool='nuclei',status='completed',completion_order=2),dict(tool='httpx',status='completed',completion_order=1)],
        findings=findings,errors=[],coverage={})
    window.render_scan()
    chosen=window.findings.currentItem().data(0,Qt.ItemDataRole.UserRole)
    def codes(visible_only=False):
        items=[window.findings.topLevelItem(i) for i in range(window.findings.topLevelItemCount())]
        ids=[item.data(0,Qt.ItemDataRole.UserRole) for item in items if not visible_only or not item.isHidden()]
        return [next(f['code'] for f in findings if f['id']==key) for key in ids]
    window.sort_order.setCurrentIndex(window.sort_order.findData('severity_desc'))
    assert codes()==['alert','http','csp','inventory']
    assert window.findings.currentItem().data(0,Qt.ItemDataRole.UserRole)==chosen
    window.sort_order.setCurrentIndex(window.sort_order.findData('completion_newest'))
    assert codes()==['alert','inventory','csp','http']
    window.tool_filter.setCurrentIndex(window.tool_filter.findData('moth'))
    window.kind_filter.setCurrentIndex(window.kind_filter.findData('configuration'))
    window.severity_filter.setCurrentIndex(window.severity_filter.findData('medium'))
    window.finding_search.setText('HTTP')
    assert codes(True)==['http']
    assert window.visible_findings.text()=='Showing 1 of 4'
    window.kind_filter.setCurrentIndex(window.kind_filter.findData('information'))
    assert codes(True)==[]
    window.reset_filters_button.click()
    assert codes(True)==['csp','http','inventory','alert']
    assert window.visible_findings.text()=='Showing 4 of 4'
    window.language_box.setCurrentIndex(window.language_box.findData('ro'))
    assert window.tool_filter.currentText()=='Toate instrumentele'
    assert window.visible_findings.text()=='Afișate: 4 din 4'


def test_scan_level_selector_is_exclusive_and_controls_consent(window,monkeypatch):
    from moth import engine
    assert window.profile=='low'
    window.profile_buttons['high'].click()
    assert window.profile=='high'
    assert window.active_consent.isVisible()
    assert sum(b.isChecked() for b in window.profile_buttons.values())==1
    window.active_consent.setChecked(True)
    window.profile_buttons['medium'].click()
    assert not window.active_consent.isVisible()
    assert not window.active_consent.isChecked()
    assert '5 pages' in window.profile_note.text()
    assert 'One website origin' in window.scope_note.text()
    window.profile_buttons['ultra'].click()
    assert window.profile=='ultra'
    assert all(c.isChecked() and not c.isEnabled() for c in window.tool_checks.values())
    assert window.extra_toggle.isChecked()
    calls=[]
    def start(*args,**kwargs):
        calls.append(kwargs)
        raise ValueError('Profile verified without starting a scan')
    monkeypatch.setattr(engine,'start',start)
    window.active_consent.setChecked(True)
    window.start_scan()
    assert calls==[dict(profile='ultra',active_authorized=True,options=window.scan_options,session=None)]
    window.language_box.setCurrentIndex(window.language_box.findData('ro'))
    assert '100 de pagini' in window.profile_note.text()


@pytest.mark.parametrize('theme',['light','dark'])
def test_profile_dialog_uses_readable_theme(window,qapp,theme):
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QLabel, QPushButton
    window.theme_box.setCurrentIndex(window.theme_box.findData(theme))
    dialog=window.create_profile_dialog()
    dialog.show()
    qapp.processEvents()
    try:
        pixel=dialog.grab().toImage().pixelColor(dialog.width()//2,8)
        text=dialog.findChild(QLabel,'qt_msgbox_label').palette().color(QPalette.ColorRole.WindowText)
        if theme=='dark':
            assert max(pixel.red(),pixel.green(),pixel.blue())<110
            assert min(text.red(),text.green(),text.blue())>180
        else:
            assert min(pixel.red(),pixel.green(),pixel.blue())>180
            assert max(text.red(),text.green(),text.blue())<100
        for button in dialog.findChildren(QPushButton):
            if 'details' in button.text().lower():
                button.click()
                qapp.processEvents()
                break
        assert dialog.palette().color(QPalette.ColorRole.Window)==window.palette().color(QPalette.ColorRole.Window)
    finally:
        dialog.close()
        dialog.deleteLater()


def test_scan_tips_rotate_pause_translate_and_stop(window,qapp):
    import copy
    window.current=dict(id='tips-test',status='running',target='https://example.com/',progress=5,stage='moth',tools=[],steps=[],findings=[],errors=[],coverage={})
    original=copy.deepcopy(window.current)
    window.render_scan()
    qapp.processEvents()
    assert window.tip_card.isVisible()
    assert window.tip_card.height() >= 164
    assert window.tip_body.height() >= 64
    assert window.tip_pause.height() >= 28
    assert window.tip_timer.isActive() and window.tip_timer.interval()==20000
    first=window.current_tip['id']
    window.tip_timer.timeout.emit()
    assert window.current_tip['id']!=first
    window.tip_pause.click()
    assert not window.tip_timer.isActive()
    assert window.tip_pause.text()=='Resume tips'
    window.next_tip()
    assert not window.tip_timer.isActive()
    window.language_box.setCurrentIndex(window.language_box.findData('ro'))
    assert window.tip_body.text()==window.current_tip['text']['ro']
    assert window.tip_pause.text()=='Reia sfaturile'
    window.tip_pause.click()
    assert window.tip_timer.isActive()
    assert window.current==original
    window.current['status']='completed'
    window.render_scan()
    assert not window.tip_card.isVisible()
    assert not window.tip_timer.isActive()


def test_spider_details_and_current_tool_estimates_are_visible(window,qapp):
    window.current=dict(id='spider-ui',status='running',target='https://example.com/',created='2026-01-01T00:00:00+00:00',progress=20,stage='zap',tools=['zap'],findings=[],errors=[],coverage={},
        steps=[dict(tool='moth',status='completed'),dict(tool='zap',status='running',started='2026-01-01T00:00:00+00:00')],
        estimates={'zap':dict(low=10,high=20,source='rough')},
        spider=dict(status='completed',html_pages=1,html_count_complete=True,discovered_urls=2,visited_urls=2,urls=[dict(url='https://example.com/page',processed=True,status_code='200',content_type='text/html'),dict(url='https://example.com/app.js',processed=True,status_code='200',content_type='application/javascript')]))
    window.render_scan()
    assert window.result_tabs.count()==7
    assert 'HTML pages: 1' in window.spider_summary.text()
    assert window.spider_urls.topLevelItemCount()==2
    assert 'Longer than estimated' in window.current_time.text()
    window.spider_search.setText('app.js')
    assert window.spider_urls.topLevelItem(0).isHidden()
    assert not window.spider_urls.topLevelItem(1).isHidden()
    window.current['status']='completed'


def test_workflow_options_dialog_session_fields_and_tabs(window, qapp):
    dialog = window.make_options_dialog()
    dialog.show()
    qapp.processEvents()
    assert not dialog.fields['session_value'].isEnabled()
    dialog.auth_box.setCurrentIndex(dialog.auth_box.findData('cookie'))
    assert dialog.fields['session_value'].isEnabled()
    assert not dialog.fields['password'].isEnabled()
    dialog.fields['session_value'].setText('session=TEMPORARY-SECRET')
    dialog.fields['account_label'].setText('qa-account')
    dialog.fields['verify_url'].setText('https://example.com/private')
    dialog.fields['verify_marker'].setText('Private account page')
    dialog.exclusions.setPlainText('/logout\n/admin')
    from PySide6.QtWidgets import QDialogButtonBox
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
    assert window.pending_session.mode == 'cookie'
    assert window.scan_options['exclude_paths'] == ['/logout', '/admin']
    assert 'TEMPORARY-SECRET' not in str(window.settings.allKeys())
    dialog.deleteLater()
    qapp.processEvents()
    window.language_box.setCurrentIndex(window.language_box.findData('ro'))
    assert window.result_tabs.tabText(4) == 'Priorități'
    assert window.result_tabs.tabText(5) == 'Compară scanări'


def test_grouped_sources_filter_and_priority_summary(window):
    from moth.findings import finding
    window.current = dict(id='grouped-ui', target='https://example.com/', created='2026-01-01T00:00:00+00:00', status='completed', progress=100, stage='finished', tools=['zap'], steps=[dict(tool='moth',status='completed'),dict(tool='zap',status='completed')], findings=[finding('csp','https://example.com/','missing'),finding('Content Security Policy (CSP) Header Not Set','https://example.com/','rule 10038','medium',tool='zap')],errors=[],coverage={})
    window.render_scan()
    assert window.findings.topLevelItemCount() == 1
    window.tool_filter.setCurrentIndex(window.tool_filter.findData('zap'))
    assert not window.findings.topLevelItem(0).isHidden()
    assert 'Sources: moth, zap' in window.explanation.toPlainText()
    assert 'rule 10038' in window.explanation.toPlainText()
    assert 'Content-Security-Policy' in window.priority_summary.toPlainText()
    assert window.recheck_button.isEnabled()


def test_missing_zap_dependencies_are_recommended_without_installing(window, monkeypatch):
    from moth import system_install, tools
    from PySide6.QtWidgets import QMessageBox, QPushButton
    calls=[]
    monkeypatch.setattr(system_install,'missing_requirements',lambda tool:['docker'])
    monkeypatch.setattr(QMessageBox,'information',lambda *args:calls.append(args[-1]))
    monkeypatch.setattr(tools,'start_install',lambda *args,**kwargs:pytest.fail('No automatic dependency install'))
    window.install_tool('zap')
    assert len(calls)==1 and 'Docker' in calls[0] and 'Requirements' in calls[0]
    assert window.findChild(QPushButton,'install_docker') is not None
    assert window.findChild(QPushButton,'install_nmap') is not None


def test_dependency_button_installs_only_chosen_program(window, monkeypatch):
    from moth import system_install, tools
    calls=[]
    monkeypatch.setattr(system_install,'missing_requirements',lambda tool:[])
    monkeypatch.setattr(tools,'start_install',lambda tool:calls.append(tool))
    window.install_tool('docker')
    assert calls==['docker']
