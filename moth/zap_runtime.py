"""Isolated ZAP daemon: observe real automation/spider state before cleanup."""
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import urllib.parse
import urllib.request
from .processes import external_environment, no_console_flags
from .targets import normalize
from .tools import is_docker_zap


class Client:
    def __init__(self, port, key):
        self.base = f'http://127.0.0.1:{port}/JSON/'
        self.key = key
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, component, kind, name, **params):
        params['apikey'] = self.key
        url = self.base + f'{component}/{kind}/{name}/?' + urllib.parse.urlencode(params)
        with self.opener.open(url, timeout=3) as response:
            raw = response.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError('ZAP API response exceeded the output size limit.')
        data = json.loads(raw)
        if isinstance(data, dict) and 'code' in data and 'message' in data:
            raise ValueError('ZAP API: ' + str(data['code']))
        return data


def spider_snapshot(client, target, headers=False, cancel=None):
    scans = client.call('spider', 'view', 'scans').get('scans', [])
    if not scans:
        return dict(status='pending', counts_known=False, discovered_urls=0, visited_urls=0, html_pages=None, urls=[])
    scan = scans[-1]
    progress = int(scan.get('progress', 0))
    result = client.call('spider', 'view', 'fullResults', scanId=scan['id'])
    records = []
    for group in result.get('fullResults', []):
        records.extend(group.get('urlsInScope', []))
    target_parts = urllib.parse.urlsplit(target)
    rows, discovered, visited, html_urls = [], set(), set(), set()
    complete_headers = headers
    for record in records:
        if cancel is not None and cancel.is_set():
            from .adapters import Cancelled
            raise Cancelled()
        raw = record.get('url', '')
        try:
            url = normalize(raw)
            if urllib.parse.urlsplit(url)[:2] != target_parts[:2]:
                continue
        except ValueError:
            continue
        discovered.add(raw)
        processed = str(record.get('processed', '')).lower() == 'true'
        if processed:
            visited.add(raw)
        row = dict(url=url, method=record.get('method', 'GET'), processed=processed,
                   status_code=record.get('statusCode', ''), content_type='')
        if headers and processed:
            try:
                message = client.call('core', 'view', 'message', id=record['messageId'])['message']
                header = message.get('responseHeader', '')
                match = re.search(r'^content-type:\s*([^\r\n;]+)', header, re.I | re.M)
                row['content_type'] = match[1].strip().lower() if match else ''
                if row['content_type'] in ('text/html', 'application/xhtml+xml'):
                    html_urls.add(url)
                del message
            except Exception:
                complete_headers = False
        rows.append(row)
    finished = progress == 100 and str(scan.get('state', '')).upper() == 'FINISHED'
    return dict(status='completed' if finished else 'running', progress=progress, counts_known=True,
                discovered_urls=len(discovered), visited_urls=len(visited),
                html_pages=len(html_urls) if headers else None, html_count_complete=complete_headers,
                urls=rows, queries_removed=True, source='ZAP spider fullResults API')


def phase_from_progress(data):
    phase = 'automation'
    for line in data.get('info', []):
        match = re.fullmatch(r'Job ([\w-]+) started', line)
        if match:
            phase = match[1]
    return phase


def run(cmd, target, directory, plan, cancel, progress=None):
    from .adapters import Cancelled
    progress = progress or (lambda details: None)
    docker_mode = is_docker_zap(cmd)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    key = secrets.token_hex(32)
    client = Client(port, key)
    directory.mkdir(parents=True, exist_ok=True)
    plan_path = directory / 'plan.yaml'
    plan_path.write_text(json.dumps(plan), encoding='utf-8')
    container = 'moth-' + hashlib.sha256(str(directory).encode()).hexdigest()[:20]
    home = directory / 'home'
    home.mkdir(exist_ok=True)
    daemon = ['-daemon', '-silent', '-port', str(port), '-config', 'api.key=' + key,
              '-config', 'autoupdate.checkOnStart=false']
    if docker_mode:
        args = [cmd[0], 'run', '--rm', '--name', container, '-p', f'127.0.0.1:{port}:{port}']
        if os.name != 'nt' and hasattr(os, 'getuid'):
            args += ['--user', f'{os.getuid()}:{os.getgid()}']
        args += ['-v', f'{directory}:/zap/wrk:rw', cmd[1], 'zap.sh'] + daemon
        args += ['-host', '0.0.0.0', '-config', 'api.addrs.addr.name=.*', '-config', 'api.addrs.addr.regex=true']
        remote_plan = '/zap/wrk/plan.yaml'
    else:
        args = cmd + daemon + ['-host', '127.0.0.1', '-dir', str(home)]
        remote_plan = str(plan_path)
    spider_enabled = any(job['type'] == 'spider' for job in plan['jobs'])
    spider = dict(status='pending' if spider_enabled else 'not_run', discovered_urls=0, visited_urls=0, html_pages=None, urls=[])
    details = dict(phase='starting', spider=spider)
    progress(details)
    process = None
    started_api = False
    completed_headers = False
    kwargs = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | no_console_flags()}
    with (directory / 'stdout.log').open('wb') as log:
        try:
            process = subprocess.Popen(args, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                       env=external_environment(), **kwargs)
            while True:
                if cancel.is_set():
                    raise Cancelled()
                if (directory / "stdout.log").stat().st_size > 8_000_000:
                    raise ValueError("ZAP output exceeded the size limit.")
                if process.poll() is not None:
                    raise ValueError('ZAP exited before its local control API was ready. Check the ZAP installation.')
                try:
                    client.call('core', 'view', 'version')
                    started_api = True
                    break
                except (OSError, ValueError):
                    cancel.wait(.3)
            plan_id = client.call('automation', 'action', 'runPlan', filePath=remote_plan)['planId']
            failures = 0
            while True:
                if cancel.is_set():
                    raise Cancelled()
                if (directory / "stdout.log").stat().st_size > 8_000_000:
                    raise ValueError("ZAP output exceeded the size limit.")
                if process.poll() is not None:
                    raise ValueError('ZAP exited before the automation plan finished.')
                try:
                    data = client.call('automation', 'view', 'planProgress', planId=plan_id)
                    failures = 0
                except (OSError, ValueError):
                    failures += 1
                    if failures >= 3:
                        raise ValueError('The local ZAP control API stopped responding.')
                    cancel.wait(1)
                    continue
                if spider_enabled:
                    try:
                        if not completed_headers:
                            spider = spider_snapshot(client, target, cancel=cancel)
                            if spider['status'] == 'completed':
                                spider = spider_snapshot(client, target, headers=True, cancel=cancel)
                                completed_headers = True
                    except (OSError, ValueError, KeyError):
                        spider['status'] = 'unavailable'
                details = dict(phase=phase_from_progress(data), spider=spider)
                progress(details)
                if data.get('finished'):
                    if data.get('error'):
                        raise ValueError('ZAP automation failed: ' + '; '.join(map(str, data['error']))[:1500])
                    break
                cancel.wait(1)
            details['phase'] = 'completed'
            progress(details)
        except BaseException:
            if spider_enabled and spider.get('status') != 'completed':
                spider['status'] = 'cancelled' if cancel.is_set() else 'failed'
            progress(dict(phase='cancelled' if cancel.is_set() else 'failed', spider=spider))
            raise
        finally:
            if started_api:
                try:
                    client.call('core', 'action', 'shutdown')
                except Exception:
                    pass
            if process is not None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15,creationflags=no_console_flags())
                    else:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    process.wait(timeout=15)
            if docker_mode:
                subprocess.run([cmd[0],'rm','-f',container],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,env=external_environment(),creationflags=no_console_flags())
