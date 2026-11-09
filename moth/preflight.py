"""Read-only preparation checks and an explicit template preparation action."""
import os
import shutil
import subprocess
import threading
from pathlib import Path
from . import tools
from .config import ROOT, TOOLS, RUNS
from .profiles import incompatibility
from .scan_options import restriction, excluded
from .processes import external_environment, no_console_flags

FLAGS = {'httpx': ('-h', ['-json', '-no-fallback-scheme']), 'katana': ('-h', ['-cs', '-cos', '-rl']),
         'nuclei': ('-h', ['-jsonl', '-dut']), 'nmap': ('--help', ['-oX', '-sT']),
         'retire': ('--help', ['--outputpath']), 'dnsx': ('-h', ['-json']),
         'subfinder': ('-h', ['-json']), 'wafw00f': ('--help', ['-r']), 'sslyze': ('--help', ['--json_out'])}


def inspect(target, selected, profile, options, authenticated=False, cancel=None):
    rows = []
    if excluded(target, options):
        rows.append(dict(tool='moth', status='error', message='The starting URL is excluded. Change the target or exclusions.'))
    for tool in selected:
        if cancel and cancel.is_set():
            from .adapters import Cancelled
            raise Cancelled()
        reason = incompatibility(tool, target) or restriction(tool, options, authenticated)
        if reason:
            rows.append(dict(tool=tool, status='skip', message=reason))
            continue
        cmd = tools.command(tool)
        if not cmd:
            rows.append(dict(tool=tool, status='error', message='Not installed. Install it on the Tools page.'))
            continue
        try:
            if tool in FLAGS:
                flag, required = FLAGS[tool]
                result = subprocess.run(cmd + [flag], capture_output=True, timeout=12, env=external_environment(), creationflags=no_console_flags())
                output = (result.stdout + result.stderr).decode(errors='replace')[:250000]
                if result.returncode not in (0, 1) or any(value not in output for value in required):
                    raise ValueError('Required CLI options are missing. Update this tool or verify its installation.')
            if tool == 'nuclei':
                path = TOOLS / 'nuclei/templates/http' if profile in ('high', 'ultra') else ROOT / 'templates'
                if not path.is_dir() or not any(path.rglob('*.yaml')):
                    raise ValueError('Nuclei templates are missing or empty. Use Prepare templates before starting.')
            if tool == 'zap' and tools.is_docker_zap(cmd):
                ready = subprocess.run([cmd[0], 'image', 'inspect', cmd[1]], capture_output=True, timeout=12, env=external_environment(), creationflags=no_console_flags())
                if ready.returncode:
                    raise ValueError('Docker or its pinned ZAP image is unavailable. Start Docker and install ZAP from Tools.')
            if tool == 'zap' and not tools.is_docker_zap(cmd):
                # ZAP checks the actual automation/API readiness at runtime as well.
                jar_dirs = [Path(cmd[0]).parent / 'plugin', Path('/usr/share/zaproxy/plugin')]
                plugins = [p.name for folder in jar_dirs if folder.is_dir() for p in folder.glob('*.zap')]
                if plugins and any(not any(name.startswith(prefix) for name in plugins) for prefix in (('automation-', 'spider-', 'reports-', 'replacer-') if authenticated else ('automation-', 'spider-', 'reports-'))):
                    raise ValueError('ZAP needs its automation, spider and reports add-ons. Update ZAP/add-ons first.')
            rows.append(dict(tool=tool, status='ready', message='Required local prerequisites checked. Target reachability and session access are checked before assessment.'))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            rows.append(dict(tool=tool, status='error', message=str(exc) if isinstance(exc, ValueError) else 'Compatibility check failed. Check the executable, required CLI options and dependencies; for Nuclei, prepare its templates.'))
    try:
        RUNS.mkdir(parents=True, exist_ok=True)
        if not os.access(RUNS, os.W_OK) or shutil.disk_usage(RUNS).free < 200_000_000:
            rows.append(dict(tool='moth', status='error', message='The data directory must be writable with at least 200 MB free.'))
        else:
            rows.append(dict(tool='moth', status='ready', message='Local data directory is writable and has at least 200 MB free. Built-in checks are available.'))
    except OSError:
        rows.append(dict(tool='moth', status='error', message='Cannot access the local data directory.'))
    return rows


def prepare_templates(cancel=None):
    from .adapters import execute
    import tempfile
    from pathlib import Path
    cmd = tools.command('nuclei')
    if not cmd:
        raise ValueError('Install Nuclei first.')
    with tempfile.TemporaryDirectory(prefix='moth-templates-') as folder:
        execute(cmd + ['-ut', '-ud', str(TOOLS / 'nuclei/templates')], Path(folder), cancel or threading.Event(), timeout=300)
    if not any((TOOLS / 'nuclei/templates/http').rglob('*.yaml')):
        raise ValueError('No HTTP templates were installed. Check connectivity and Nuclei compatibility.')
