import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from moth.targets import normalize, fetch, resolve
from moth.checks import basic
from moth import engine, storage


@pytest.fixture
def website():
    class Handler(BaseHTTPRequestHandler):
        requests = []

        def do_GET(self):
            self.requests.append(self.path)
            self.send_response(302 if self.path == "/redirect" else 200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "session=DO-NOT-STORE-THIS; Path=/")
            if self.path == "/redirect":
                self.send_header("Location", "/never-follow?token=SECRET")
            self.end_headers()
            self.wfile.write(b"<html><h1>Lab</h1></html>")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", Handler
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:secret@example.com", "https://-bad.example", "http://example.com:99999", "https://example.com\nX:test", "https://a..com", "http://example.com:0"])
def test_invalid_targets(url):
    with pytest.raises(ValueError):
        normalize(url)


def test_url_secrets_are_removed():
    assert normalize("Example.com/path?token=SECRET#fragment") == "https://example.com/path"
    assert normalize("https://example.com/știri") == "https://example.com/%C8%99tiri"


def test_private_targets_require_opt_in(website):
    url, _ = website
    with pytest.raises(ValueError, match="laboratory"):
        resolve(url)
    assert resolve(url, True) == ["127.0.0.1"]


def test_real_http_findings_and_redaction(website):
    url, _ = website
    findings, coverage = basic(url, True)
    codes = {f["code"] for f in findings}
    assert {"http", "csp", "frame", "nosniff", "cookie_secure", "cookie_httponly", "cookie_samesite"} <= codes
    assert coverage["http_status"] == 200
    assert "DO-NOT-STORE-THIS" not in str(findings)
    assert all(set(f["text"]) == {"en", "ro", "ru"} for f in findings)


def test_redirects_are_not_followed(website):
    url, handler = website
    findings, coverage = basic(url + "/redirect", True)
    assert handler.requests == ["/redirect"]
    assert any(f["code"] == "redirect" for f in findings)
    assert "SECRET" not in str(findings)


def test_engine_stores_real_scan(website):
    url, _ = website
    scan_id = engine.start(url, [], True, True)
    deadline = time.monotonic() + 5
    while scan_id in engine.ACTIVE and time.monotonic() < deadline:
        time.sleep(.02)
    result = storage.get(scan_id)
    assert result["status"] == "completed"
    assert result["findings"]
    assert result["progress"] == 100


def test_failed_scan_is_not_clean_scan(monkeypatch):
    monkeypatch.setattr(engine, "resolve", lambda *args: (_ for _ in ()).throw(ValueError("DNS failed")))
    scan_id = engine.start("https://invalid.example", [], True)
    deadline = time.monotonic() + 5
    while scan_id in engine.ACTIVE and time.monotonic() < deadline:
        time.sleep(.02)
    result = storage.get(scan_id)
    assert result["status"] == "failed"
    assert result["errors"]


def test_permission_required():
    with pytest.raises(ValueError, match="permission"):
        engine.start("https://example.com", [], False)


def test_certificate_expiry_and_disabled_hsts(monkeypatch):
    from moth import checks
    import ssl
    expires = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(time.time() + 10 * 86400))
    monkeypatch.setattr(checks, "fetch", lambda *args: (200, [("Content-Type", "text/html"), ("Strict-Transport-Security", "max-age=0")], b"", {"notAfter": expires}))
    findings, coverage = checks.basic("https://example.com")
    assert {"certificate_expiring", "hsts"} <= {f["code"] for f in findings}
    assert 9 <= coverage["certificate_days_remaining"] <= 10


def test_invalid_certificate_never_falls_back(monkeypatch):
    from moth import checks
    import ssl
    def invalid(*args):
        raise ssl.SSLCertVerificationError("untrusted certificate")
    monkeypatch.setattr(checks, "fetch", invalid)
    findings, coverage = checks.basic("https://example.com")
    assert [f["code"] for f in findings] == ["certificate"]
    assert coverage["http_status"] is None
