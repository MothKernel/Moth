import sqlite3
import pytest
from moth import storage
from moth.findings import finding
from moth.reports import render


def test_report_escapes_external_content():
    scan = dict(id="abc", created=storage.now(), status="completed", target="https://example.com/", findings=[finding("<script>alert(1)</script>", "https://example.com/", '<img src=x onerror="alert(1)">')], coverage={}, errors=[])
    report = render(scan)
    assert "<script>" not in report
    assert "&lt;script&gt;" in report
    assert "&lt;img" in report


def test_translated_report_and_persistence():
    scan = dict(id="abc", created=storage.now(), status="completed", target="https://example.com/", findings=[], coverage={}, errors=[])
    storage.save(scan)
    assert storage.get("abc") == scan
    assert storage.recent()[0]["id"] == "abc"
    assert "Отчёт" in render(scan, "ru")


def test_restart_recovery():
    storage.save(dict(id="interrupted", created=storage.now(), status="running"))
    storage.recover()
    assert storage.get("interrupted")["status"] == "interrupted"


def test_database_handles_are_closed():
    with storage.connect() as db:
        db.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")


def test_html_report_includes_escaped_preflight_diagnostics():
    scan=dict(id='preflight-example',target='https://example.com/',created='2026-11-09',status='failed',findings=[],errors=[],preflight=[dict(tool='nuclei',status='error',message='Templates missing <script>alert(1)</script>')])
    report=render(scan)
    assert 'Diagnostics' in report and 'nuclei' in report
    assert 'Templates missing &lt;script&gt;' in report
    assert '<script>alert(1)</script>' not in report
