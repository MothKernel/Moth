import hashlib
import json
import sys
import threading
import time
import zipfile
import pytest
from moth import tools, adapters


def test_checksum_rejects_tampering(tmp_path):
    archive = tmp_path / "tool.zip"
    archive.write_bytes(b"original")
    checksum = tmp_path / "checksums.txt"
    checksum.write_text(hashlib.sha256(b"original").hexdigest() + "  tool.zip\n")
    tools.verify_checksum(archive, checksum)
    archive.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        tools.verify_checksum(archive, checksum)


def test_installer_only_extracts_expected_binary(monkeypatch, tmp_path):
    system, arch = tools.native_platform()
    name = f"httpx_1.0_{system}_{arch}.zip"
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../../escaped.txt", "bad")
        z.writestr("httpx" + tools.EXE, "binary")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    release = {"tag_name": "v1.0", "assets": [{"name": name, "browser_download_url": "https://upstream/archive"}, {"name": "httpx_checksums.txt", "browser_download_url": "https://upstream/checksums"}]}
    monkeypatch.setattr(tools, "remote_json", lambda *a: release)
    def download(url, destination, *args):
        destination.write_bytes(archive.read_bytes() if url.endswith("archive") else f"{digest}  {name}\n".encode())
    monkeypatch.setattr(tools, "download", download)
    folder = tmp_path / "installed"
    folder.mkdir()
    tools.install_pd("httpx", folder)
    assert (folder / ("httpx" + tools.EXE)).read_text() == "binary"
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_tool_failure_does_not_mark_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "TOOLS", tmp_path)
    monkeypatch.setattr(tools, "install_pd", lambda *args: (_ for _ in ()).throw(ValueError("bad checksum")))
    tools.install("httpx")
    assert tools.STATE["httpx"]["status"] == "error"
    assert tools.command("httpx") is None
    tools.STATE.clear()


def test_process_cancelled_and_reaped(tmp_path):
    cancel = threading.Event()
    timer = threading.Timer(.2, cancel.set)
    timer.start()
    start = time.monotonic()
    with pytest.raises(adapters.Cancelled):
        adapters.execute([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, cancel)
    timer.join()
    assert time.monotonic() - start < 5


@pytest.mark.parametrize("tool,row", [
    ("httpx", {"status_code": 200, "title": "Site", "request": "SECRET"}),
    ("katana", {"request": {"endpoint": "https://example.com/path?token=SECRET"}}),
    ("nuclei", {"template-id": "moth-check", "info": {"name": "Missing policy", "severity": "info"}, "request": "SECRET"}),
    ("dnsx", {"host": "example.com", "a": ["203.0.113.1"]}),
    ("subfinder", {"host": "sub.example.com"}),
])
def test_jsonl_adapters_preserve_safe_fields(tool, row, tmp_path):
    found = adapters.parse(tool, "https://example.com/", json.dumps(row), tmp_path)
    assert found and found[0]["tool"] == tool
    assert "SECRET" not in str(found)


@pytest.mark.parametrize("tool,filename,data", [
    ("wafw00f", "result.json", [{"firewall": "Example WAF"}]),
    ("sslyze", "result.json", {"server_scan_results": [{"scan_status": "COMPLETED", "scan_result": {"tls_1_0_cipher_suites": {"result": {"accepted_cipher_suites": ["cipher"]}}}}]}),
    ("retire", "result.json", {"data": [{"results": [{"component": "lib", "version": "1", "vulnerabilities": [{"identifiers": {"CVE": ["CVE-EXAMPLE"]}}]}]}]}),
    ("zap", "result.json", {"site": [{"alerts": [{"name": "Header absent", "riskcode": "1", "desc": "<p>Review</p>", "solution": "Fix"}]}]}),
])
def test_file_adapters(tool, filename, data, tmp_path):
    (tmp_path / filename).write_text(json.dumps(data))
    assert adapters.parse(tool, "https://example.com/", "", tmp_path)


def test_nmap_adapter(tmp_path):
    (tmp_path / "result.xml").write_text('<nmaprun><host><ports><port portid="443"><state state="open"/></port></ports></host></nmaprun>')
    result = adapters.parse("nmap", "https://example.com/", "", tmp_path)
    assert result[0]["severity"] == "info"


def test_empty_probe_is_a_failure(tmp_path):
    with pytest.raises(ValueError, match="did not return"):
        adapters.parse("httpx", "https://example.com", "", tmp_path)
