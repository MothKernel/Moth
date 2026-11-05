# Moth 0.2 status

Moth is now a native Qt Widgets desktop program. Version 0.1's web server and browser frontend have been removed. The engine, saved history and installed tools are retained.

## Implemented

- Native desktop window, direct Python engine calls, no HTTP server or WebView.
- English/Romanian/Russian interface with persistent language preference.
- Assessments, progress, stop, plain-language findings and technical details.
- Ten integration adapters and tool installation/detection within the window.
- Native history view and HTML/JSON save dialogs.
- Desktop shortcut creation and single-instance protection.
- Linux executable build and Windows executable build workflow.
- Offscreen native widget tests and core engine tests.

## Remaining validation and improvements

- Exercise all third-party installer/runtime combinations on clean Windows and Linux machines. Core and parser tests are not substitutes for these checks.
- Expand reviewed Nuclei templates and translated mappings for external findings.
- Pin supported scanner versions and test their upgrade paths.
- Add authenticated assessment with careful secret handling.
- Add a signed installer/update channel after executable and scanner validation.

Windows packaged builds do not require a separate Python installation for Moth itself. The two optional Python-based scanners still require an external Python runtime, reported explicitly by the tool manager. ZAP requires Docker; Nmap uses its official installation.
