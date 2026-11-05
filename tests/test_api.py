import json
import pytest
from fastapi.testclient import TestClient
from moth.app import app, TOKEN
from moth import storage
from moth.findings import finding
from moth.reports import render


@pytest.fixture
def client():
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def test_local_session_required(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/tools").status_code == 403
    response = client.get("/api/tools", headers={"X-Moth-Token": TOKEN})
    assert response.status_code == 200
    assert len(response.json()) == 10


def test_origin_and_host_guards(client):
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 403
    assert client.post("/api/scans", headers={"Origin": "https://evil.example", "X-Moth-Token": TOKEN}, json={"target":"example.com", "authorized":True}).status_code == 403


def test_validation_and_missing_scan(client):
    headers = {"X-Moth-Token": TOKEN}
    assert client.post("/api/scans", headers=headers, json={"target": "example.com"}).status_code == 400
    assert client.get("/api/scans/no-such-id", headers=headers).status_code == 404
    assert client.post("/api/tools/unknown/install", headers=headers).status_code == 400


def test_report_escapes_external_content():
    scan = dict(id="abc", created=storage.now(), status="completed", target="https://example.com/", findings=[finding("<script>alert(1)</script>", "https://example.com/", '<img src=x onerror="alert(1)">')], coverage={}, errors=[])
    report = render(scan)
    assert "<script>" not in report
    assert "&lt;script&gt;" in report
    assert "&lt;img" in report


def test_history_and_report(client):
    scan = dict(id="abc", created=storage.now(), status="completed", target="https://example.com/", findings=[], coverage={}, errors=[])
    storage.save(scan)
    headers={"X-Moth-Token":TOKEN}
    assert client.get("/api/scans", headers=headers).json()[0]["finding_count"] == 0
    response = client.get("/api/scans/abc/report?format=html&language=ru", headers=headers)
    assert "Отчёт" in response.text
    assert client.get("/api/scans/abc/report?format=json", headers=headers).json()["id"] == "abc"


def test_restart_recovery():
    storage.save(dict(id="interrupted", created=storage.now(), status="running"))
    storage.recover()
    assert storage.get("interrupted")["status"] == "interrupted"
