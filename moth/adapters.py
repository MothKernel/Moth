"""Bounded CLI adapters. Tool observations remain distinct from verified vulnerabilities."""
import json
import os
import re
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from .config import ROOT
from .findings import finding
from .targets import fetch, normalize, resolve
from .tools import command, is_docker_zap
from .processes import external_environment, no_console_flags


class Cancelled(Exception):
    pass


def execute(args, directory, cancel, timeout=180, stdin=None, accepted=(0,)):
    """File-backed output avoids pipe deadlocks; process groups support cancellation."""
    log = directory / "stdout.log"
    error = directory / "stderr.log"
    kwargs = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | no_console_flags()}
    with log.open("wb") as out, error.open("wb") as err:
        process = subprocess.Popen(args, cwd=directory, stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                   stdout=out, stderr=err, env=external_environment(), **kwargs)
        if stdin:
            try:
                process.stdin.write(stdin.encode())
                process.stdin.close()
            except BrokenPipeError:
                pass
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if cancel.wait(.15):
                    raise Cancelled()
                if time.monotonic() > deadline:
                    raise ValueError("Tool exceeded its execution time limit.")
                if log.stat().st_size + error.stat().st_size > 8_000_000:
                    raise ValueError("Tool output exceeded the size limit.")
            if cancel.is_set():
                raise Cancelled()
            if process.returncode not in accepted:
                detail = error.read_text(encoding="utf-8", errors="replace")[-2000:]
                raise ValueError(f"Tool exited with code {process.returncode}: {detail}")
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15, creationflags=no_console_flags())
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait(timeout=15)
    return log.read_text(encoding="utf-8", errors="replace")[:8_000_000]


def json_lines(output):
    rows = []
    for line in output.splitlines():
        if line.strip():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except json.JSONDecodeError:
                continue
    return rows


def observation(tool, url, title, details, severity="info", explanation=None, recommendation=None):
    item = finding(title, url, details, severity, "information" if severity == "info" else "review", tool=tool)
    for lang in item["text"]:
        item["text"][lang] = [title, explanation or "Reported by the external tool. Review the evidence and the tool's coverage before drawing a conclusion.", recommendation or "Review this observation in its application context."]
    item["source_language"] = "en"
    return item


def parse(tool, url, output, directory):
    """Never store raw HTTP responses, cookie values or full scan output in findings."""
    items = []
    rows = json_lines(output)
    if tool == "httpx":
        if not rows:
            raise ValueError("httpx did not return a web response. Check reachability and the selected protocol.")
        for row in rows[:10]:
            safe = {key: row[key] for key in ("status_code", "title", "webserver", "tech", "host", "port") if key in row}
            items.append(observation(tool, url, "Web service observed", json.dumps(safe, ensure_ascii=False)))
    elif tool == "katana":
        seen = set()
        for row in rows:
            endpoint = row.get("request", {}).get("endpoint", "")
            try:
                cleaned = normalize(endpoint)
                if urlsplit(cleaned).netloc != urlsplit(url).netloc:
                    continue
            except ValueError:
                continue
            seen.add(cleaned)
        if seen:
            items.append(observation(tool, url, "Pages discovered", "\n".join(sorted(seen)[:50])))
    elif tool == "nuclei":
        for row in rows[:100]:
            info = row.get("info", {})
            items.append(observation(tool, url, info.get("name", "Template matched"),
                                     "Template: " + str(row.get("template-id", "unknown")),
                                     info.get("severity", "info"), info.get("description"), info.get("remediation")))
    elif tool in ("dnsx", "subfinder"):
        safe = []
        for row in rows[:100]:
            safe.append({key: row[key] for key in ("host", "a", "aaaa", "cname", "mx", "ns", "source") if key in row})
        if safe:
            items.append(observation(tool, url, "DNS records" if tool == "dnsx" else "Subdomains discovered (not scanned)",
                                     json.dumps(safe, ensure_ascii=False)[:3000]))
    elif tool == "wafw00f":
        path = directory / "result.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        items.append(observation(tool, url, "Firewall identification result", json.dumps(data, ensure_ascii=False)[:2000],
                                 explanation="Firewall detection is heuristic. Detection or non-detection does not establish site security."))
    elif tool == "sslyze":
        data = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        if not data.get("server_scan_results"):
            raise ValueError("SSLyze returned no server analysis.")
        errors = [r for r in data.get("server_scan_results", []) if r.get("scan_status") == "ERROR" or r.get("connectivity_status") == "ERROR"]
        if errors:
            raise ValueError("SSLyze could not complete the TLS analysis. Check connectivity and the selected port.")
        # The Mozilla compliance result is a policy assessment, not proof of exploitation.
        compliance = data.get("mozilla_configurations", {})
        results = data.get("server_scan_results", [])
        safe = {"servers_analyzed": len(results), "mozilla_policy": compliance}
        items.append(observation(tool, url, "TLS configuration analysis completed", json.dumps(safe, ensure_ascii=False)[:2500],
                                 explanation="SSLyze completed its analysis. This summary is informational; no blanket security verdict is assigned."))
        for server in results:
            scan = server.get("scan_result") or {}
            for key, label in (("ssl_2_0_cipher_suites", "SSL 2.0"), ("ssl_3_0_cipher_suites", "SSL 3.0"),
                               ("tls_1_0_cipher_suites", "TLS 1.0"), ("tls_1_1_cipher_suites", "TLS 1.1")):
                result = (scan.get(key) or {}).get("result") or {}
                if result.get("accepted_cipher_suites"):
                    items.append(observation(tool, url, "Legacy TLS protocol supported", label, "medium",
                                             recommendation="Review client compatibility and disable obsolete protocol versions."))
    elif tool == "retire":
        path = directory / "result.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data.get("data", [])[:50]:
            for result in entry.get("results", []):
                if result.get("vulnerabilities"):
                    safe = {key: result.get(key) for key in ("component", "version", "vulnerabilities")}
                    items.append(observation(tool, url, "JavaScript library with known advisories", json.dumps(safe)[:2500], "medium",
                                             recommendation="Verify the detected version and update to a maintained release. Exploitability needs manual review."))
    elif tool == "nmap":
        tree = ET.fromstring((directory / "result.xml").read_text(encoding="utf-8"))
        for port in tree.findall(".//port"):
            state = port.find("state")
            if state is not None:
                items.append(observation(tool, url, "Web port observed", f"TCP {port.get('portid')}: {state.get('state')}"))
    elif tool == "zap":
        report = directory / "result.json"
        if not report.exists():
            raise ValueError("ZAP did not produce the requested JSON report.")
        data = json.loads(report.read_text(encoding="utf-8"))
        if not data.get("site"):
            raise ValueError("ZAP produced no site data. The page may not have been reachable from Docker.")
        severity = {"0": "info", "1": "low", "2": "medium", "3": "high"}
        for site in data.get("site", []):
            for alert in site.get("alerts", [])[:100]:
                # Avoid reflecting request bodies or authentication material from instances.
                items.append(observation(tool, url, alert.get("name", "ZAP alert"),
                                         f"ZAP rule {alert.get('pluginid', '?')}; confidence {alert.get('confidence', '?')}",
                                         severity.get(str(alert.get("riskcode")), "info"),
                                         re.sub(r"<[^>]+>", "", alert.get("desc", "")),
                                         re.sub(r"<[^>]+>", "", alert.get("solution", ""))))
    return items


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.sources += [value for key, value in attrs if key == "src" and value]


def run_tool(tool, url, directory, cancel, allow_private=False):
    cmd = command(tool)
    if not cmd:
        raise ValueError("Tool is not installed. Open Tools to install it.")
    directory.mkdir(parents=True, exist_ok=True)
    p = urlsplit(url)
    addresses = resolve(url, allow_private)
    stdin = None
    accepted = (0,)
    if tool == "httpx":
        args = cmd + ["-u", url, "-json", "-silent", "-duc", "-status-code", "-title", "-tech-detect", "-no-fallback-scheme", "-threads", "1", "-rate-limit", "2", "-timeout", "10", "-response-size-to-read", "524288"]
    elif tool == "katana":
        scope = "^" + re.escape(f"{p.scheme}://{p.netloc}") + r"(?:/|$)"
        args = cmd + ["-u", url, "-jsonl", "-silent", "-d", "2", "-cs", scope, "-dr", "-ct", "30s", "-c", "1", "-p", "1", "-rl", "2", "-mrs", "524288", "-iqp"]
    elif tool == "nuclei":
        args = cmd + ["-u", url, "-t", str(ROOT / "templates"), "-jsonl", "-silent", "-duc", "-dr", "-c", "1", "-rl", "2", "-timeout", "10", "-retries", "0", "-omit-raw"]
    elif tool == "dnsx":
        args = cmd + ["-json", "-silent", "-a", "-aaaa", "-cname", "-resp", "-t", "1", "-rl", "2"]
        stdin = p.hostname + "\n"
    elif tool == "subfinder":
        args = cmd + ["-d", p.hostname, "-json", "-silent", "-rl", "2", "-timeout", "10", "-max-time", "1"]
    elif tool == "sslyze":
        if p.scheme != "https":
            raise ValueError("Select an HTTPS URL for SSLyze.")
        args = cmd + ["--json_out", str(directory / "result.json"), f"{p.hostname}:{p.port or 443}"]
    elif tool == "wafw00f":
        args = cmd + [url, "-f", "json", "-o", str(directory / "result.json"), "-r"]
    elif tool == "retire":
        source = directory / "scripts"
        source.mkdir(exist_ok=True)
        status, headers, body, cert = fetch(url, allow_private)
        parser = Scripts()
        parser.feed(body.decode("utf-8", "replace"))
        # Analyze the page's inline scripts plus up to five same-origin scripts.
        (source / "page.js").write_bytes(body)
        for index, src in enumerate(parser.sources[:5]):
            if cancel.is_set():
                raise Cancelled()
            candidate = normalize(urljoin(url, src))
            if urlsplit(candidate).netloc != p.netloc or urlsplit(candidate).scheme != p.scheme:
                continue
            code, _, script, _ = fetch(candidate, allow_private)
            if code == 200:
                (source / f"script-{index}.js").write_bytes(script)
        args = cmd + ["--path", str(source), "--outputformat", "json", "--outputpath", str(directory / "result.json"), "--exitwith", "0"]
    elif tool == "nmap":
        # Scan only the resolved target address and explicitly selected web port; no NSE or OS scans.
        args = cmd + (["-6"] if ":" in addresses[0] else []) + ["-sT", "-Pn", "-n", "--max-retries", "1", "--host-timeout", "30s", "-p", str(p.port or (443 if p.scheme == "https" else 80)), "-oX", str(directory / "result.xml"), addresses[0]]
    elif tool == "zap":
        docker_mode = is_docker_zap(cmd)
        report_dir = "/zap/wrk" if docker_mode else str(directory)
        plan = {"env": {"contexts": [{"name": "moth", "urls": [url]}], "parameters": {"failOnError": True}},
                "jobs": [{"type": "requestor", "requests": [{"url": url, "method": "GET", "httpVersion": "HTTP/1.1"}]},
                         {"type": "passiveScan-wait", "parameters": {"maxDuration": 1}},
                         {"type": "report", "parameters": {"template": "traditional-json", "reportDir": report_dir, "reportFile": "result.json"}}]}
        (directory / "plan.yaml").write_text(json.dumps(plan))
        if docker_mode:
            docker, image = cmd
            container = "moth-" + directory.parent.name
            args = [docker, "run", "--rm", "--name", container]
            if os.name != "nt" and hasattr(os, "getuid"):
                args += ["--user", f"{os.getuid()}:{os.getgid()}"]
            args += ["-v", f"{directory}:/zap/wrk:rw", image, "zap.sh", "-cmd", "-autorun", "/zap/wrk/plan.yaml"]
        else:
            args = cmd + ["-cmd", "-dir", str(directory / "home"), "-autorun", str(directory / "plan.yaml")]
        accepted = (0, 2)  # automation warnings can yield exit 2
    else:
        raise ValueError("Unsupported tool.")
    try:
        output = execute(args, directory, cancel, timeout=240 if tool == "zap" else 180, stdin=stdin, accepted=accepted)
        return parse(tool, url, output, directory)
    finally:
        if tool == "zap" and is_docker_zap(cmd):
            # docker client termination alone does not stop the container.
            subprocess.run([cmd[0], "rm", "-f", "moth-" + directory.parent.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, env=external_environment(), creationflags=no_console_flags())
        # Raw output may contain cookies, request material or URLs with tokens.
        for path in directory.rglob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
