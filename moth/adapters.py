"""Bounded CLI adapters. Tool observations remain distinct from verified vulnerabilities."""
from datetime import datetime, timezone
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


# Subfinder uses context.WithTimeout even for 0, which cancels immediately.
# This positive horizon (~190 years) removes a practical CLI scan deadline
# without overflowing Go time.Duration; Moth still supports immediate Stop.
SUBFINDER_NO_DEADLINE_MINUTES = 100_000_000


class Cancelled(Exception):
    pass


def execute(args, directory, cancel, timeout=180, stdin=None, accepted=(0,), progress=None):
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
        deadline = time.monotonic() + timeout if timeout is not None else None
        last_progress = 0
        try:
            while process.poll() is None:
                if progress and time.monotonic() - last_progress >= 1:
                    progress()
                    last_progress = time.monotonic()
                if cancel.wait(.15):
                    raise Cancelled()
                if deadline is not None and time.monotonic() > deadline:
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
    from .presentation import describe
    item["text"] = {lang: list(describe(item, lang)) for lang in ("en", "ro", "ru")}
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
            safe = {key: row[key] for key in ("status_code", "title", "webserver", "tech", "host", "port", "content_type", "content_length", "a", "http2", "tls") if key in row}
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
            safe.append({key: row[key] for key in ("host", "a", "aaaa", "cname", "mx", "ns", "txt", "soa", "srv", "ptr", "caa", "axfr", "source") if key in row})
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
        if any(host.get("timedout") == "true" for host in tree.findall(".//host")):
            raise ValueError("Nmap reached its host time limit; port coverage is incomplete.")
        for port in tree.findall(".//port"):
            state = port.find("state")
            if state is not None:
                details = f"TCP {port.get('portid')}: {state.get('state')}"
                service = port.find("service")
                if service is not None:
                    details += "\n" + json.dumps(service.attrib, ensure_ascii=False)
                for script in port.findall("script"):
                    details += "\n" + script.get("id", "NSE") + ": " + script.get("output", "")[:1500]
                items.append(observation(tool, url, "Web port observed", details))
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


def run_tool(tool, url, directory, cancel, allow_private=False, profile="low", progress=None, options=None, session=None):
    from .profiles import get_profile
    from .config import TOOLS
    settings = get_profile(profile)
    from .scan_options import validate, excluded, exclusion_regexes
    options = validate(options)
    headers = session.headers if session else {}
    if excluded(url, options):
        raise ValueError("The target URL is excluded.")
    cmd = command(tool)
    if not cmd:
        raise ValueError("Tool is not installed. Open Tools to install it.")
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    p = urlsplit(url)
    addresses = resolve(url, allow_private)
    stdin = None
    accepted = (0,)
    if tool == "httpx":
        args = cmd + ["-u", url, "-json", "-silent", "-duc", "-status-code", "-title", "-tech-detect", "-no-fallback-scheme", "-threads", "1", "-rate-limit", str(options["rate"]), "-timeout", "10", "-response-size-to-read", "524288"]
        if profile != "low":
            args += ["-content-type", "-content-length", "-ip", "-http2", "-tls-grab"]
    elif tool == "katana":
        scope = "^" + re.escape(f"{p.scheme}://{p.netloc}") + r"(?:/|$)"
        args = cmd + ["-u", url, "-jsonl", "-silent", "-d", str(settings["depth"]), "-cs", scope, "-dr", "-c", "1", "-p", "1", "-rl", str(options["rate"]), "-mrs", "524288", "-iqp"]
        args += ["-cos", r"(?i)/(?:logout|signout|delete|remove|destroy)(?:/|\?|$)"]
        for pattern in exclusion_regexes(url, options):
            args += ["-cos", pattern]
        if headers:
            header_file = directory / "session-headers.txt"
            header_file.write_text("\n".join(k + ": " + v for k, v in headers.items()), encoding="utf-8")
            header_file.chmod(0o600)
            args += ["-H", str(header_file)]
        if settings["js"]:
            args += ["-jc"]
            if not headers and not options["exclude_paths"]:
                args += ["-kf", "all"]
        if profile == "ultra":
            args += ["-jsl"]
    elif tool == "nuclei":
        templates = ROOT / "templates"
        if profile == "low":
            templates = templates / "moth-missing-csp.yaml"
        elif profile in ("high", "ultra"):
            templates = TOOLS / "nuclei/templates/http"
            if not templates.is_dir():
                execute(cmd + ["-ut", "-ud", str(templates.parent)], directory, cancel, timeout=None)
            if not templates.is_dir():
                raise ValueError("The official Nuclei HTTP templates could not be prepared.")
        args = cmd + ["-u", url, "-t", str(templates), "-jsonl", "-silent", "-duc", "-dr", "-c", "1", "-rl", str(options["rate"]), "-timeout", "10", "-retries", "0", "-omit-raw"]
        if profile in ("high", "ultra"):
            args += ["-pt", "http", "-dut", "-ni", "-etags", "dos,fuzz,bruteforce,creds-stuffing,token-spray"]
            if profile == "high":
                args += ["-tags", "tech,exposure,misconfig"]
    elif tool == "dnsx":
        args = cmd + ["-json", "-silent", "-a", "-aaaa", "-cname", "-resp", "-t", "1", "-rl", str(options["rate"])]
        if profile != "low":
            args += ["-mx", "-ns", "-txt", "-soa"]
        if profile == "ultra":
            args += ["-srv", "-ptr", "-caa", "-axfr"]
        stdin = p.hostname + "\n"
    elif tool == "subfinder":
        args = cmd + ["-d", p.hostname, "-json", "-silent", "-rl", str(options["rate"]), "-timeout", "10", "-max-time", str(SUBFINDER_NO_DEADLINE_MINUTES)]
        if profile in ("high", "ultra"):
            args += ["-all"]
    elif tool == "sslyze":
        if p.scheme != "https":
            raise ValueError("Select an HTTPS URL for SSLyze.")
        args = cmd + ["--json_out", str(directory / "result.json")]
        if profile == "low":
            args += ["--certinfo", "--tlsv1_2", "--tlsv1_3"]
        elif profile == "medium":
            args += ["--certinfo", "--sslv2", "--sslv3", "--tlsv1", "--tlsv1_1", "--tlsv1_2", "--tlsv1_3"]
        # With no explicit scan commands, SSLyze runs its complete default suite.
        args += [f"{'[' + p.hostname + ']' if ':' in p.hostname else p.hostname}:{p.port or 443}"]
    elif tool == "wafw00f":
        args = cmd + [url, "-f", "json", "-o", str(directory / "result.json"), "-r"]
        if profile in ("high", "ultra"):
            args += ["-a"]
    elif tool == "retire":
        source = directory / "scripts"
        source.mkdir(exist_ok=True)
        status, headers, body, cert = fetch(url, allow_private, **({"headers": headers} if headers else {}))
        parser = Scripts()
        parser.feed(body.decode("utf-8", "replace"))
        # Analyze the page's inline scripts plus up to five same-origin scripts.
        (source / "page.js").write_bytes(body)
        scripts_checked = 0
        for index, src in enumerate(parser.sources[:settings["scripts"]]):
            if cancel.is_set():
                raise Cancelled()
            candidate = normalize(urljoin(url, src))
            if urlsplit(candidate).netloc != p.netloc or urlsplit(candidate).scheme != p.scheme:
                continue
            if excluded(candidate, options):
                continue
            if cancel.wait(1 / options["rate"]):
                raise Cancelled()
            code, _, script, _ = fetch(candidate, allow_private, **({"headers": headers} if headers else {}))
            scripts_checked += 1
            if progress:
                progress(dict(phase="scripts", scripts_checked=scripts_checked, percent=None, last_activity=datetime.now(timezone.utc).isoformat()))
            if code == 200:
                (source / f"script-{index}.js").write_bytes(script)
        args = cmd + ["--path", str(source), "--outputformat", "json", "--outputpath", str(directory / "result.json"), "--exitwith", "0"]
    elif tool == "nmap":
        args = cmd + (["-6"] if ":" in addresses[0] else []) + ["-sT", "-Pn", "-n", "--max-retries", "1", "--max-rate", str(options["nmap_rate"]), "--stats-every", "2s", "-v"]
        port = str(p.port or (443 if p.scheme == "https" else 80))
        if options["ports"]:
            args += ["-p", options["ports"]]
        elif settings["ports"] == "all":
            args += ["-p", "1-65535"]
        elif settings["ports"] == "common":
            common = "21,22,23,25,53,80,110,111,135,139,143,161,389,443,445,465,587,636,993,995,1433,1521,2049,3306,3389,5432,5900,6379,8000,8080,8443,9200,27017"
            args += ["-p", common + "," + port]
        else:
            args += ["-p", port]
        if profile != "low":
            args += ["-sV", "--version-light" if profile != "ultra" else "--version-all"]
        if profile in ("high", "ultra"):
            args += ["--script", "http-title,http-headers,http-security-headers,ssl-cert,ssl-enum-ciphers"]
        args += ["-oX", str(directory / "result.xml"), addresses[0]]
    elif tool == "zap":
        docker_mode = is_docker_zap(cmd)
        report_dir = "/zap/wrk" if docker_mode else str(directory)
        origin = f"{p.scheme}://{p.netloc}"
        context = {"name": "moth", "urls": [url], "includePaths": ["^" + re.escape(origin) + r"(?:/.*)?$"],
                   "excludePaths": [r"(?i)^" + re.escape(origin) + r"/.*(?:logout|signout|delete|destroy).*"]}
        context["excludePaths"] += exclusion_regexes(url, options)
        jobs = [{"type": "requestor", "requests": [{"url": url, "method": "GET", "httpVersion": "HTTP/1.1"}]}]
        if headers:
            origin_regex = "^" + re.escape(origin) + r"(?:/.*)?$"
            jobs.insert(0, {"type": "replacer", "rules": [dict(description="Moth session " + name, url=origin_regex, matchType="req_header", matchString=name, matchRegex=False, replacementString=value) for name, value in headers.items()]})
        if settings["spider"]:
            jobs.append({"type": "spider", "parameters": {"context": "moth", "url": url, "maxDuration": 0,
                         "maxDepth": settings["depth"], "maxChildren": settings["pages"], "threadCount": 1,
                         "logoutAvoidance": True, "postForm": False, "processForm": True, "parseRobotsTxt": not bool(options["exclude_paths"]), "parseSitemapXml": not bool(options["exclude_paths"])}})
        jobs.append({"type": "passiveScan-wait", "parameters": {"maxDuration": 0}})
        if settings["active"]:
            jobs.append({"type": "activeScan", "parameters": {"context": "moth", "url": url,
                "maxScanDurationInMins": 0, "maxRuleDurationInMins": 0,
                "threadPerHost": 1, "delayInMs": max(1, int(1000 / options["rate"])), "addQueryParam": True, "scanHeadersAllRequests": profile == "ultra"},
                "policyDefinition": {"defaultStrength": "High" if profile == "ultra" else "Medium", "defaultThreshold": "Low" if profile == "ultra" else "Medium"}})
            jobs.append({"type": "passiveScan-wait", "parameters": {"maxDuration": 0}})
        jobs.append({"type": "report", "parameters": {"template": "traditional-json", "reportDir": report_dir, "reportFile": "result.json"}})
        plan = {"env": {"contexts": [context], "parameters": {"failOnError": True}}, "jobs": jobs}
    else:
        raise ValueError("Unsupported tool.")
    # Private run directory protects transient header/configuration files.
    directory.chmod(0o700)
    try:
        if tool == "zap":
            from .zap_runtime import run as run_zap
            run_zap(cmd, url, directory, plan, cancel, progress)
            output = ""
        else:
            kwargs = {}
            if progress:
                from .tool_progress import snapshot
                kwargs['progress'] = lambda: progress(snapshot(tool, directory))
            output = execute(args, directory, cancel, timeout=None, stdin=stdin, accepted=accepted, **kwargs)
        return parse(tool, url, output, directory)
    finally:
        # Raw output may contain cookies, request material or URLs with tokens.
        for path in directory.rglob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
