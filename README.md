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

Create or refresh the shortcut from the program's **Desktop shortcut** button, or run:

```bash
python install_desktop.py
```

### Windows

The **Desktop build** GitHub Actions workflow produces a **Moth-Windows** artifact. Download and extract the complete ZIP, then double-click **Moth.exe**. Keep the `_internal` directory beside the executable. The packaged application includes Python and Qt for its own operation.

Use **Desktop shortcut** inside Moth to create a Windows desktop shortcut.

To run the source checkout instead, install Python 3.11+ with its launcher, then double-click `start.bat`. The source launcher installs dependencies and opens the native window with `pythonw.exe`.

## Features

- Built-in HTTP(S) checks: certificate validation/expiry, HTTP use, security headers, cookie attributes and redirects.
- Background assessments with progress, stop controls and explicit failure/partial states.
- Findings list with plain-language explanations and a separate technical-details view.
- Ten tool integrations, optional tool selection and installation from the Tools page.
- Local SQLite history, reopened directly inside the program.
- Native save dialogs for standalone HTML and JSON reports. HTML is an export format, not the program interface.
- English, Romanian and Russian interface and built-in finding explanations; language selection persists.
- Desktop shortcuts and a single-instance lock.

## Optional tools

| Tool | Installation | Current adapter scope |
| --- | --- | --- |
| httpx (ProjectDiscovery) | Official release, SHA-256 checked | HTTP service identification; no redirects or protocol fallback |
| SSLyze | Isolated Python environment | TLS configuration summary and legacy protocol detection |
| Katana | Official release, SHA-256 checked | Exact-origin crawl, depth 2, 30 seconds, 2 requests/second |
| ZAP | Docker image, pinned by digest | One-page passive analysis; no active scan or spider |
| Nuclei | Official release, SHA-256 checked | Reviewed template bundled with Moth, not the full community library |
| Retire.js | Local npm installation; verified Node LTS if needed | Page and up to five same-origin scripts |
| dnsx | Official release, SHA-256 checked | A, AAAA and CNAME records |
| WAFW00F | Isolated Python environment | WAF fingerprinting, redirects disabled |
| Subfinder | Official release, SHA-256 checked | Passive discovery; discovered hosts are not scanned |
| Nmap | Official installation detected | TCP connect to the selected web port on one resolved address |

ZAP requires Docker Desktop/Engine installed and running. Nmap uses an official, separate installation due to redistribution restrictions. SSLyze and WAFW00F need a separate Python 3.11+ installation when using the packaged executable; the UI identifies that prerequisite. Installing system drivers, Docker or Python is not performed silently. Tools install under Moth's user data directory, without administrator privileges.

Installations need internet access. Some tool databases and passive discovery sources also use external services. Missing platform builds, upstream API limits or runtime incompatibilities are shown as installation errors with a retry option. Not all external installers have been exercised on Windows yet.

## Assessment scope and local data

Assess targets you own or have permission to test. Private/local targets require the laboratory option. Crawlers and scanners generate additional requests; even GET requests can affect poorly designed sites.

The built-in checker retrieves one initial URL, does not follow redirects, validates TLS, pins the connection to a resolved address and excludes URL query strings, fragments and embedded credentials. External scanners use their own network stacks; CLI scope controls are not an operating-system network sandbox.

Missing hardening, open ports and identified technologies are not automatically vulnerabilities. No findings is not a security guarantee. Tool errors and limited coverage remain visible. External scanner descriptions are currently shown in their original English and labeled accordingly.

Data is stored under `%LOCALAPPDATA%/Moth` on Windows and `~/.local/share/Moth` on Linux. Set `MOTH_DATA_DIR` to override it. Existing assessment history and tool installations from version 0.1 are reused. Raw tool artifacts are removed after each run; normalized findings omit raw response and cookie values. Exported reports can contain target addresses and technical evidence.

## Development and packaging

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Native UI tests use Qt's offscreen platform and exercise actual Qt widgets: language changes, navigation, a local lab assessment, technical details, history and file exports. Engine tests cover scope checks, cancellation, redaction, installer integrity, result parsers and SQLite lifecycle. They do not install every scanner.

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
