"""Background update discovery. Checks metadata only; installation needs a click."""
import os
import re
from pathlib import Path
import shlex
import tempfile
import threading
import time
import urllib.request
from . import tools

LOCK = threading.Lock()
RESULTS = {}
WORKER = None
LAST_CHECK = 0
LAST_SIGNATURE = None
INTERVAL = 6 * 60 * 60


def version_number(value):
    value = value.strip().removeprefix('v')
    if re.search(r'(?:dev|alpha|beta|rc|snapshot)', value, re.I):
        return None
    match = re.fullmatch(r'(\d+(?:\.\d+){1,3})(?:[-+]\d+)?', value)
    if not match:
        return None
    parts = tuple(map(int, match[1].split('.')))
    return parts + (0,) * (4 - len(parts))


def installed_version(row):
    if row['source'] in ('moth', 'docker') and row['version']:
        return row['version']
    tool = row['id']
    cmd = tools.command(tool)
    if not cmd:
        raise ValueError('Tool is no longer installed.')
    if tool == 'zap':
        jars = [part for part in cmd if re.search(r'zap-\d.*\.jar$', part)]
        if not jars:
            jars = list(Path(cmd[0]).resolve().parent.glob('zap-*.jar'))
        if len(jars) == 1:
            match = re.fullmatch(r'zap-(\d+(?:\.\d+)+)\.jar', str(jars[0]).replace('\\', '/').split('/')[-1])
            if match:
                return match[1]
        raise ValueError('Installed ZAP version could not be determined without starting ZAP.')
    from .adapters import execute
    if tool == 'sslyze':
        # SSLyze has no --version switch. Query metadata with its own Python.
        executable = Path(cmd[0])
        python = executable.parent / ('python.exe' if os.name == 'nt' else 'python')
        if python.is_file():
            args = [str(python)]
        else:
            try:
                with executable.open('rb') as script:
                    line = script.readline(1024).decode('utf-8').strip()
                args = shlex.split(line[2:]) if line.startswith('#!') else []
                if not any('python' in Path(arg).name.lower() for arg in args):
                    raise ValueError('Python interpreter for SSLyze could not be determined.')
            except (OSError, UnicodeError) as exc:
                raise ValueError('Python interpreter for SSLyze could not be determined.') from exc
        args += ['-I', '-c', "import importlib.metadata; print(importlib.metadata.version('sslyze'))"]
    else:
        flag = '-version' if tool in tools.PD else '--version' if tool in ('nmap', 'retire') else '-V'
        args = cmd + [flag]
    with tempfile.TemporaryDirectory(prefix='moth-version-') as tmp:
        text = execute(args, Path(tmp), threading.Event(), timeout=15)
        text += "\n" + (Path(tmp) / "stderr.log").read_text(encoding="utf-8", errors="replace")[:32000]
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    patterns = {
        'nmap': r'Nmap version\s+(\d+(?:\.\d+)+)',
        'sslyze': r'(?:sslyze\s+)?(\d+\.\d+\.\d+)',
        'retire': r'^\s*(\d+\.\d+\.\d+)\s*$',
        'zap': r'(?:ZAP\s+)?(\d+\.\d+\.\d+)',
    }
    pattern = patterns.get(tool, r'(?:version[:\s]*|\bv)(\d+(?:\.\d+){1,3})')
    match = re.search(pattern, text, re.I | re.M)
    if not match:
        raise ValueError('Installed version could not be determined.')
    # A prerelease binary must not be presented as an older stable build.
    if re.search(r'(?:dev|alpha|beta|rc|snapshot)', text[match.start():match.end()+20], re.I):
        raise ValueError('Installed version is a development or prerelease build.')
    return match[1]


def latest_version(tool):
    if tool in tools.PD:
        data = tools.remote_json(f'https://api.github.com/repos/projectdiscovery/{tool}/releases/latest')
        return data['tag_name']
    if tool in ('sslyze', 'wafw00f'):
        return tools.remote_json(f'https://pypi.org/pypi/{tool}/json')['info']['version']
    if tool == 'retire':
        return tools.remote_json('https://registry.npmjs.org/retire/latest')['version']
    if tool == 'zap':
        return tools.remote_json('https://api.github.com/repos/zaproxy/zaproxy/releases/latest')['tag_name']
    request = urllib.request.Request('https://nmap.org/download.html', headers={'User-Agent': 'Moth'})
    with urllib.request.urlopen(request, timeout=20) as response:
        text = response.read(1_000_000).decode('utf-8', 'replace')
    match = re.search(r'nmap-(\d+(?:\.\d+)+)-setup\.exe', text)
    if not match:
        raise ValueError('Latest Nmap release could not be determined.')
    return match[1]


def latest_zap_digest():
    token = tools.remote_json('https://ghcr.io/token?service=ghcr.io&scope=repository:zaproxy/zaproxy:pull')['token']
    request = urllib.request.Request('https://ghcr.io/v2/zaproxy/zaproxy/manifests/stable', method='HEAD', headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json',
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        digest = response.headers.get('Docker-Content-Digest', '')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('Latest container digest could not be determined.')
    return 'ghcr.io/zaproxy/zaproxy@' + digest


def check(row):
    current = installed_version(row)
    if row['source'] == 'docker':
        latest = latest_zap_digest()
        available = current != latest
    else:
        latest = latest_version(row['id'])
        old, new = version_number(current), version_number(latest)
        if old is None or new is None:
            raise ValueError('Version format could not be compared reliably.')
        available = new > old
    return dict(update_status='available' if available else 'current', installed_version=current,
                latest_version=latest, update_error='')


def snapshot():
    with LOCK:
        return {key: dict(value) for key, value in RESULTS.items()}


def invalidate(tool):
    global LAST_CHECK
    with LOCK:
        RESULTS.pop(tool, None)
        LAST_CHECK = 0


def _run(rows):
    global WORKER
    try:
        for row in rows:
            try:
                result = check(row)
            except Exception as exc:
                result = dict(update_status='error', update_error=str(exc)[:300])
            result['update_location'] = row['location']
            result['update_version'] = row['version']
            with LOCK:
                RESULTS[row['id']] = result
    finally:
        with LOCK:
            WORKER = None


def request_check(rows, force=False):
    global WORKER, LAST_CHECK, LAST_SIGNATURE
    rows = [dict(row) for row in rows if row['status'] == 'ready']
    signature = tuple((r['id'], r['location'], r['version']) for r in rows)
    with LOCK:
        if WORKER is not None:
            return
        if not force and signature == LAST_SIGNATURE and time.monotonic() - LAST_CHECK < INTERVAL:
            return
        LAST_SIGNATURE, LAST_CHECK = signature, time.monotonic()
        for row in rows:
            RESULTS[row['id']] = dict(update_status='checking', update_location=row['location'], update_version=row['version'])
        WORKER = threading.Thread(target=_run, args=(rows,), daemon=True)
        WORKER.start()
