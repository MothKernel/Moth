# Moth status and roadmap

Moth 0.2 is a native Qt Widgets desktop program. The browser frontend has been removed; local history and managed tools are retained.

## Implemented

- Native desktop UI, English/Romanian/Russian, persistent light/dark theme and language preferences.
- Ten scanner integrations, automatic installation detection, queued tool installation and update actions.
- Low/Medium/High/Ultra profiles, approximate time estimates and recorded tool timings.
- Real Nmap phase/ZAP progress where available; output activity for other adapters.
- Whole-assessment Stop and Skip current tool with partial coverage retained.
- Grouping of known equivalent header findings, with original sources and evidence preserved.
- Baseline comparison and targeted finding rechecks, with conservative handling of mismatched/incomplete scope.
- Excluded path prefixes, custom TCP ports and independent rate controls.
- Ephemeral cookie/Bearer/HTTP Basic sessions for supported adapters, verified against a private page.
- Priority recommendations, visible execution errors and coverage limits.
- Prerequisite/CLI checks and explicit preparation of official Nuclei templates.
- ZAP spider URL/HTML counts, local SQLite history, standalone HTML/JSON exports.
- Desktop shortcuts, single-instance protection, local Linux packaging and Windows build workflow.
- Native widget/core tests; local ZAP/Katana authentication and Nmap progress integration checks.

## Proposed next work — not implemented

- Manual finding states, analyst notes, false-positive decisions and risk acceptance.
- Saved projects/targets with reusable non-secret configuration.
- PDF reporting for technical and nontechnical audiences.
- Detection of rate limiting/service overload and adaptive request pacing.
- Browser-rendered crawling for JavaScript applications.
- OpenAPI import and selected API endpoint assessment.
- Signed installation packages and an update channel for Moth itself.
- Repeatable regression labs measuring findings, missed cases and false positives.

## Remaining validation

- Exercise every third-party installer/runtime combination on clean Windows and Linux systems.
- Test supported scanner versions and their upgrade paths; expand reviewed translations/mappings.
- Expand authenticated-session validation across adapters, failure modes and platform builds.

Windows packages include Python/Qt for Moth itself. Optional Python-based scanners still require a separate Python runtime. Native ZAP is supported; Docker is only required for its container variant. Nmap uses a separate official installation.
