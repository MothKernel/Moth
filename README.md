# Moth

Moth is a native desktop website security assessment program with optional scanner integrations, plain-language findings, technical details, and actionable recommendations.

**Version 0.2 — native Qt/PySide6 desktop application.** Moth opens its own window. There is no HTTP server, browser interface, Electron shell, or embedded web view. English is the default language; Romanian and Russian are available from the language selector.

![Moth desktop application](docs/moth-interface.png)

## Launch from your desktop

### Linux

On the development computer, double-click **Moth** on the desktop or find Moth in the applications menu. The shortcut points to the native executable in `dist/Moth/Moth` when a local build exists.

To run from source:

```bash
bash start.sh
```

The launcher creates a virtual environment and installs Qt if necessary. On Linux it can reuse a distribution-installed PySide6. No terminal is needed when launching the desktop shortcut.

Create or refresh the desktop shortcut with:

```bash
python install_desktop.py
```

### Windows

The **Desktop build** GitHub Actions workflow produces a **Moth-Windows** artifact. Download and extract the complete ZIP, then double-click **Moth.exe**. Keep the `_internal` directory beside the executable. The packaged application includes Python and Qt for its own operation.

To create a desktop shortcut from a source checkout, run `python install_desktop.py`.

To run the source checkout instead, install Python 3.11+ with its launcher, then double-click `start.bat`. The source launcher installs dependencies and opens the native window with `pythonw.exe`.

## Features

- Built-in HTTP(S) checks: certificate validation/expiry, HTTP use, security headers, cookie attributes and redirects.
- Background assessments with progress, stop controls and explicit failure/partial states.
- Searchable findings with combined severity, tool and result-type filters, visible-result counts and a reset control. Sort by severity (both directions), tool completion (both directions), tool name or finding title. New assessments record check start/end times and completion order; older assessments use their recorded sequential check order. Findings include specific plain-language explanations, visible evidence and a separate technical-details view.
- Dedicated Errors and Checks & coverage tabs: execution failures include explanations, suggested actions and the original message; each selected tool shows its status and scope. Older saved observations receive the improved descriptions when opened.
- Ten tool integrations, automatic detection of existing installations, optional selection and installation from the Tools page.
- Automatic background update checks on startup, after installed tools change and every six hours while open; a manual **Check updates** button is available. Moth offers updates without installing them automatically. Managed tools use the installation queue; system tools show package-manager/official-installer guidance.
- FIFO installation queue: select multiple tools and they install one at a time; failures do not block the next tool. The queue lasts for the current app session.
- Local SQLite history, reopened directly inside the program.
- Native save dialogs for standalone HTML and JSON reports. HTML is an export format, not the program interface.
- English, Romanian and Russian interface and built-in finding explanations; language selection persists.
- Light and dark themes from the header selector; the selected theme persists, including profile/message dialogs.
- While scanning, 18 offline tips rotate every 20 seconds across cybersecurity, Moth usage and moth natural history. Next/pause/resume controls affect only tips; source links open only on a click. All tips are available in English, Romanian and Russian.
- Color-coded tool status badges: green for installed, amber for missing/prerequisites, blue while installing and red for errors.
- Desktop shortcuts and a single-instance lock.

## Scan levels

Choose one of **Low / Medium / High / Ultra** above the target form; the options are mutually exclusive. Low is the default. **Profile details** shows the exact supported scope for every integration. High/Ultra require explicit permission for active requests and additional server ports, which can modify application data.

| Profile | Built-in pages | Katana depth | Nuclei | ZAP | Nmap |
| --- | --- | --- | --- | --- | --- |
| Low | 1 | 1, no duration cap | Bundled CSP check | One-page passive | Website port |
| Medium | Up to 5 | 3, JS parsing | Bundled header checks | Passive + spider, no duration cap | Website port + service detection |
| High | Up to 20 | 5, JS parsing | Signed HTTP technology/exposure/misconfiguration templates | Spider + active scan, no duration cap | 33 common TCP ports plus website port, service detection and selected web/TLS NSE scripts |
| Ultra | Up to 100 | 10, JS + jsluice | Standard signed HTTP templates | Spider + active scan at High strength, no duration cap | All 65,535 TCP ports, all service probes and selected web/TLS NSE scripts |

Medium also increases HTTP probes, DNS record types, TLS protocols and JavaScript files analyzed by Retire.js. High/Ultra enable SSLyze's default full suite, all WAFW00F signatures and all available passive Subfinder sources; Ultra adds DNS AXFR/CAA/SRV/PTR queries. Retire.js script limits are 5 / 15 / 30 / 100. There is no Moth scan-wide or tool-wide duration deadline. ZAP spider/active/passive-wait duration caps are set to zero (unlimited), Katana's crawl timer and Nmap host/NSE timers are omitted, and process execution remains cancellable. Subfinder's upstream implementation treats zero as immediate cancellation, so its positive horizon is set to 100,000,000 minutes (within Go's duration range); Moth imposes no separate deadline. Page/depth limits, rate controls, per-request network timeouts and bounded outputs remain in effect.

The overview shows elapsed and approximate remaining time for the whole scan and the current tool. Estimates start from broad heuristics; after three completed runs of the same tool/profile without duration caps, they use observed durations. Older capped runs and failures are not used as training samples. If an estimate is exceeded, remaining time becomes unknown; the scanner is not stopped and the estimate is not reset to a fake countdown.

**ZAP Spider** has its own tab, with confirmed status, discovered/visited URL counts, unique HTML-page counts and a searchable URL table. An isolated loopback ZAP API with a per-run key reads `spider/fullResults` and response headers. HTML pages are counted separately from scripts and other resources; unknown or incomplete metadata is labeled accordingly. URLs are normalized to remove credentials/query strings/fragments. Response bodies, cookies, API keys and raw scanner logs are not retained. Results survive in history/JSON/HTML, including confirmed spider data when later jobs fail. Old scans without retained spider telemetry show "not recorded" rather than inferred counts. Native and Docker runs are stopped/cleaned up through the same cancellation path; Docker exposes its API on host loopback only.

Ultra selects all integrations. Compatible tools must be installed before it starts; incompatible checks (for example TLS on HTTP, or DNS/subdomain discovery for an IP address) are marked **Skipped** with their reason. Low/Medium/High use the manually selected optional tools. Levels, configured limits and scope are saved with the assessment and included in reports/Checks & coverage. Old records retain their original scope.

**Ultra does not mean every possible tool switch.** Login credentials, browser workflows, OS/UDP scans, brute-force/DoS, external OAST callbacks and unsupported/mutually exclusive modes are not included. A URL cannot describe those targets and dependencies. Nuclei's initial High/Ultra run downloads official templates into Moth's data directory; only signed HTTP templates are used, with disruptive tags excluded and OAST disabled. Missing prerequisites and interrupted/failed checks remain visible. Tool-level scope controls are not an OS network sandbox.

The profile implementation follows [ZAP automation](https://www.zaproxy.org/docs/desktop/addons/automation-framework/job-ascan/), [Nuclei template selection](https://docs.projectdiscovery.io/opensource/nuclei/running), and [Nmap options](https://nmap.org/book/man-briefoptions.html).

## Optional tools

Moth checks the system PATH and common desktop/user installation locations, including `/usr/bin`, `/usr/local/bin`, `~/.local/bin`, `~/go/bin`, configured GOPATH directories and common npm locations. Existing installations take priority over Moth-managed copies. The Tools page shows the source and executable path; detection refreshes automatically and can also be refreshed manually. Python HTTPX is distinguished from ProjectDiscovery httpx by its CLI capabilities.

| Tool | Installation | Low profile adapter scope |
| --- | --- | --- |
| httpx (ProjectDiscovery) | Official release, SHA-256 checked | HTTP service identification; no redirects or protocol fallback |
| SSLyze | Isolated Python environment | TLS configuration summary and legacy protocol detection |
| Katana | Official release, SHA-256 checked | Exact-origin crawl, depth 1, no duration cap, 2 requests/second |
| ZAP | Existing native installation, or Docker image pinned by digest | One-page passive analysis; no active scan or spider |
| Nuclei | Official release, SHA-256 checked | Reviewed template bundled with Moth, not the full community library |
| Retire.js | Local npm installation; verified Node LTS if needed | Page and up to five same-origin scripts |
| dnsx | Official release, SHA-256 checked | A, AAAA and CNAME records |
| WAFW00F | Isolated Python environment | WAF fingerprinting, redirects disabled |
| Subfinder | Official release, SHA-256 checked | Passive discovery; discovered hosts are not scanned |
| Nmap | Official installation detected | TCP connect to the selected web port on one resolved address |

The table describes Low; the scan-level table above defines expanded scope. An existing native ZAP installation is used directly without Docker. On Arch, Moth uses `/usr/share/zaproxy/zap.sh` because the distribution launcher can discard command-line arguments. Docker Desktop/Engine is required only for the optional Docker-based ZAP installation. Nmap uses an official, separate installation due to redistribution restrictions. SSLyze and WAFW00F need a separate Python 3.11+ installation when using the packaged executable; the UI identifies that prerequisite. Installing system drivers, Docker or Python is not performed silently. Tools install under Moth's user data directory, without administrator privileges.

Installations need internet access. Some tool databases and passive discovery sources also use external services. Missing platform builds, upstream API limits or runtime incompatibilities are shown as installation errors with a retry option. Not all external installers have been exercised on Windows yet.

## Tool update checks

Update checks contact official upstream metadata: [GitHub releases](https://docs.github.com/en/rest/releases/releases#get-the-latest-release) for ProjectDiscovery and native ZAP, [PyPI JSON](https://docs.pypi.org/api/json/) for SSLyze/WAFW00F, the npm registry for Retire.js, Nmap's official download page, and the GHCR stable-image digest for Docker ZAP. The UI shows installed/latest versions, available updates, checking status and failures. Unknown versions and offline/rate-limited checks are not marked up to date. Checks are throttled in memory for the current session.

Click **Update** to enqueue a managed tool upgrade. Python integrations use `pip install --upgrade` inside their isolated environments; binary downloads retain checksum verification; Docker upgrades repin the stable image digest. Scans using a queued/updating tool must wait. Tools installed outside Moth are not overwritten: update them through their original package manager or official installer, refresh detection, and check again. A distribution may backport fixes without matching the latest upstream version; the badge compares upstream versions only.

## Assessment scope and local data

Assess targets you own or have permission to test. Private/local targets require the laboratory option. Crawlers and scanners generate additional requests; even GET requests can affect poorly designed sites.

The built-in checker retrieves one initial URL in Low and bounded same-origin pages at higher levels, does not follow redirects, validates TLS, pins the connection to a resolved address and excludes URL query strings, fragments and embedded credentials. External scanners use their own network stacks; CLI scope controls are not an operating-system network sandbox.

Missing hardening, open ports and identified technologies are not automatically vulnerabilities. No findings is not a security guarantee. Tool errors and limited coverage remain visible. External scanner descriptions are currently shown in their original English and labeled accordingly.

Data is stored under `%LOCALAPPDATA%/Moth` on Windows and `~/.local/share/Moth` on Linux. Set `MOTH_DATA_DIR` to override it. Existing assessment history and tool installations from version 0.1 are reused. Raw tool artifacts are removed after each run; normalized findings omit raw response and cookie values. Exported reports can contain target addresses and technical evidence.

## Development and packaging

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Native UI tests use Qt's offscreen platform and exercise actual Qt widgets: language changes, navigation, a local lab assessment, technical details, history and file exports. Engine tests cover scope checks, cancellation, redaction, installer integrity, result parsers and SQLite lifecycle. They do not install every scanner.

Minimal Ubuntu/headless environments also need `libegl1` and `libopengl0` for Qt. The test workflow installs these system libraries before running the native widget tests.

Build a native executable on the target OS:

```bash
python -m pip install "pyinstaller>=6.15,<7"
python -m PyInstaller --noconfirm Moth.spec
```

The output is `dist/Moth/Moth.exe` on Windows and `dist/Moth/Moth` on Linux, plus required libraries in `_internal`. `--smoke-test` opens the native window and closes it automatically for packaging checks. Builds are OS-specific; a Linux build is not a Windows executable.

Project layout:

```text
main.py                 Native desktop launcher
moth/desktop.py         Qt Widgets interface
moth/shortcuts.py       Desktop shortcut integration
moth/engine.py          Background scan lifecycle
moth/checks.py          Built-in checks
moth/targets.py         URL validation and bounded HTTP requests
moth/tools.py           Registry, detection and installers
moth/adapters.py        External tool execution and normalized findings
moth/processes.py       External process environment handling
moth/findings.py        Reviewed translated explanations
moth/storage.py         SQLite persistence
moth/reports.py         Standalone exported reports
moth/resources/         Translations and application icons
moth/templates/         Reviewed Nuclei templates
Moth.spec               Native executable build specification
```
