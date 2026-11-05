"""Opt-in local integration check; installs httpx through Moth's own API."""
import json
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = "http://127.0.0.1:8765"
with urllib.request.urlopen(BASE) as response:
    token = re.search(r'name="moth-token" content="([^"]+)"', response.read().decode())[1]


def api(path, body=None):
    request = urllib.request.Request(BASE + "/api/" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Moth-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


class Lab(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Set-Cookie", "session=LAB-ONLY; Path=/")
        self.end_headers()
        self.wfile.write(b"<html><title>Moth local lab</title><h1>Local lab</h1></html>")

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Lab)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    tools = api("tools")
    if next(t for t in tools if t["id"] == "httpx")["status"] != "ready":
        api("tools/httpx/install", {})
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        tool = next(t for t in api("tools") if t["id"] == "httpx")
        if tool["status"] == "ready":
            break
        if tool["status"] == "error":
            raise RuntimeError(tool["message"])
        time.sleep(2)
    else:
        raise TimeoutError("httpx installation timed out")
    print("PASS: managed httpx available through the API", flush=True)
    selected = ["httpx"]
    if next(t for t in tools if t["id"] == "nmap")["status"] == "ready":
        selected.append("nmap")
    result = api("scans", {"target": f"http://127.0.0.1:{server.server_port}", "authorized": True, "allow_private": True, "tools": selected})
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        scan = api("scans/" + result["id"])
        if scan["status"] not in ("queued", "running"):
            break
        time.sleep(.3)
    assert scan["status"] == "completed", scan["errors"]
    assert any(f["tool"] == "httpx" for f in scan["findings"]), scan
    if "nmap" in selected:
        assert any(f["tool"] == "nmap" for f in scan["findings"]), scan
    assert "LAB-ONLY" not in json.dumps(scan)
    print("PASS: real " + ", ".join(selected) + " + built-in checks against the local lab; cookie redaction", flush=True)
finally:
    server.shutdown()
    server.server_close()
