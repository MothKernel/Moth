# Moth delivery status

| Stage | Status in 0.1 |
| --- | --- |
| Define initial scope | Documented in README; local, single-user, authorized targets |
| Python assessment engine | Implemented; real local HTTP tests |
| Shared finding format | Implemented with severity, kind, confidence, evidence and translated explanations |
| Background execution | Implemented with progress, limits, cancellation and failure states |
| Ten integrations | Adapters and installation/detection paths implemented; all result parsers have fixture tests |
| Understandable explanations | Built-in findings translated into English, Romanian and Russian; original external descriptions labeled as English |
| Interface | Browser-tested: language persistence, ten tool cards, real scan, technical details, history, HTML download and mobile layout; no JavaScript errors |
| Persistence and reports | SQLite, downloadable HTML/JSON; PDF through browser printing |
| Validation | Core suite passed on Linux and Windows with Python 3.12/3.14; real httpx installation and httpx/Nmap lab scans passed on Linux; browser checks passed |
| Windows distribution | Source launcher prepared and core CI passed; full scanner installation on clean Windows and executable installer still pending |

## Before a production release

- Validate all scanner installations on a clean Windows machine; the core Windows/Linux CI matrix is already passing.
- Exercise the eight remaining external tools end to end against controlled labs, including Docker permissions and cancellation.
- Pin compatible scanner versions and test upgrades; current installers resolve upstream releases at installation time.
- Expand reviewed Nuclei templates and localized mappings for external alerts.
- Add optional authenticated assessment with careful secret handling.
- Package and test a Windows installer; resolve each redistribution license and runtime requirement.

## Optional manual verification scripts

Start Moth first. These scripts create their own local lab servers and leave assessment history in the current Moth data directory.

```bash
# Downloads the official httpx binary through Moth's own tool manager.
python scripts/verify_live.py

# Requires: pip install playwright; python -m playwright install chromium --only-shell
# Uses the previously installed httpx integration.
python scripts/check_ui.py
```

External scanners are not installed or executed by the normal pytest suite. No public website is scanned by these verification scripts.
