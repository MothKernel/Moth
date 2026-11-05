# Moth

Moth is a website security assessment tool that brings multiple scanners into a simple interface, with plain-language findings, technical details, and actionable recommendations.

**Version 0.1 — local development preview.** English is the default interface language, with Romanian and Russian available in the language selector. The interface runs in your browser; the assessment engine runs on your computer.

![Moth desktop interface](docs/moth-interface.png)

## Start

Requires Python 3.11+ with `venv` and `pip`. Python 3.12 is a useful choice for the widest third-party scanner compatibility.

Linux/macOS:

```bash
bash start.sh
```

Windows: install Python with the Python launcher, then double-click `start.bat`.

Or start manually:

```bash
python -m venv .venv
# Activate the virtual environment for your operating system.
python -m pip install -r requirements.txt
python main.py
```

Moth opens `http://127.0.0.1:8765`. Use `--no-browser` or `--port 8766` when needed. This preview is source-based; it is not yet a signed Windows executable installer.

## What works

- Built-in, bounded HTTP(S) assessment: certificate validation, HTTP use, security headers, cookie attributes and redirects.
- Background scans, progress, cancellation, explicit failure/partial states and restart recovery.
- SQLite history and standalone HTML / JSON reports. Open an HTML report and print to PDF if needed.
- Reviewed built-in finding explanations in English, Romanian and Russian.
- Optional tool selection and one-at-a-time installation from the Tools screen.
- External tool observations kept distinct from confirmed vulnerabilities. Their original descriptions remain in English; the interface identifies this explicitly.

## Optional integrations

| Tool | Installation | Current adapter scope |
| --- | --- | --- |
| httpx (ProjectDiscovery) | Official GitHub release, SHA-256 checked | HTTP service identification, no redirect following or protocol fallback |
| SSLyze | Dedicated Python virtual environment, PyPI | TLS configuration summary and legacy protocol detection |
| Katana | Official GitHub release, SHA-256 checked | Exact-origin crawl, depth 2, 30 seconds, 2 requests/second |
| ZAP | Docker image, pinned by digest after pull | One requested page and passive rules; no active scan or spider |
| Nuclei | Official GitHub release, SHA-256 checked | Only the reviewed template bundled in `moth/templates`; no arbitrary template input |
| Retire.js | npm, local prefix; verified Node LTS downloaded if absent | Initial page and up to five same-origin scripts; no third-party script fetching |
| dnsx | Official GitHub release, SHA-256 checked | Target A, AAAA and CNAME queries |
| WAFW00F | Dedicated Python virtual environment, PyPI | WAF fingerprinting, redirects disabled |
| Subfinder | Official GitHub release, SHA-256 checked | Passive discovery only; discovered hosts are never automatically scanned |
| Nmap | Official installation detected on PATH / standard Windows paths | TCP connect to the selected web port on one resolved address |

ZAP requires Docker Desktop/Engine installed and running. Nmap uses the official installer because Nmap/Npcap redistribution has licensing restrictions. These prerequisites are shown in the interface; Moth does not silently install system drivers, Docker or WSL. Other modules install within Moth's user data directory, without administrator privileges. Internet access is required for installation and some external tool databases/services.

GitHub API rate limits, network restrictions, missing platform builds or third-party runtime compatibility can cause an installation to fail. The interface shows the failure and permits a retry. Checksums protect download integrity; they are not independent proof of upstream authenticity.

## Coverage and operation

Assess only targets you own or are authorized to test. Start with a lab. Crawling and external scanners make additional requests, and even GET requests can have effects on poorly designed sites.

The built-in checker requests only the initial URL, does not follow redirects, validates TLS, ignores proxy environment variables, and pins its connection to the resolved address. Query strings, credentials and fragments are excluded. Local/private addresses require an explicit laboratory option.

External tools have their own network stacks and DNS behavior; Moth's CLI scope controls are not an OS-level network sandbox. The current app is **local and single-user**, not a hosted scanner for untrusted users. Dockerized ZAP cannot reach the host's loopback address as if it were the host itself. Use an accessible lab hostname/address for that module.

Missing headers, open ports and detected technologies are not automatically vulnerabilities. No findings is not a security guarantee. Built-in checks do not test authenticated workflows, business logic, SQL injection, XSS exploitation or every OWASP category. Tool errors and limited coverage are part of the report.

Moth removes raw tool artifacts after a run and excludes raw response/cookie values from normalized findings. Target paths, public DNS records, tool evidence and scan history remain on disk. External scanners may maintain their own upstream caches/configuration.

Data defaults to `%LOCALAPPDATA%\Moth` on Windows and `~/.local/share/Moth` on Linux. Override with `MOTH_DATA_DIR` before startup. The local API uses a per-launch session token, same-origin checks and loopback host restrictions; do not expose it through a public proxy.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests exercise a local HTTP fixture, authorization and local API controls, failed scan handling, cookie redaction, redirect scope, cancellation, installer checksums/extraction, all ten result parsers, database handle cleanup and report escaping. They do not install or run all third-party scanners. The core test suite has passed GitHub Actions on Linux and Windows with Python 3.12 and 3.14. Full scanner installation on clean Windows systems remains to be validated.

Project layout:

```text
main.py                 Local launcher
moth/app.py             FastAPI routes and local session controls
moth/engine.py          Background scan lifecycle
moth/checks.py          Built-in checks
moth/targets.py         URL validation and bounded HTTP requests
moth/tools.py           Registry, detection and installers
moth/adapters.py        External process execution and normalization
moth/findings.py        Reviewed, translated explanations
moth/storage.py         SQLite persistence
moth/reports.py         Standalone report generation
moth/static/            Interface and translations
moth/templates/         Reviewed Nuclei templates
tests/                  Automated tests
```

Next release work: test every integration against pinned upstream versions on clean Windows/Linux machines, expand reviewed checks and localized external finding mappings, then build a Windows installer and update mechanism. Review each third-party license before bundling or redistribution.
