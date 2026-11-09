import copy
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
import pytest
from moth import engine, storage, preflight, adapters, results
from moth.scan_options import validate, excluded, exclusion_regexes, restriction
from moth.session import Session
from moth.findings import finding
from moth.tool_progress import snapshot


@pytest.fixture
def website():
    class Handler(BaseHTTPRequestHandler):
        requests = []
        def do_GET(self):
            authenticated = self.headers.get('Cookie') == 'session=PRIVATE-SESSION-TOKEN'
            self.requests.append((self.path, authenticated))
            self.send_response(200 if authenticated or self.path != '/private' else 401)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write((('PRIVATE ACCOUNT PAGE' if authenticated else 'Public login page') + '<a href="/excluded">excluded</a><a href="/allowed">allowed</a>').encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}', Handler.requests
    server.shutdown()
    server.server_close()


def wait_scan(identifier):
    deadline = time.monotonic() + 8
    while identifier in engine.ACTIVE and time.monotonic() < deadline:
        time.sleep(.02)
    assert identifier not in engine.ACTIVE
    return storage.get(identifier)


def test_scope_validation_and_prefix_boundaries():
    options = validate(dict(exclude_paths='/logout\n/admin', ports='80,443,8000-8010', rate=7, nmap_rate=800))
    assert excluded('https://example.com/admin/users', options)
    assert excluded('https://example.com/%61dmin', options)
    assert not excluded('https://example.com/administrator', options)
    assert exclusion_regexes('https://example.com', options)
    for invalid in ('0', '65536', '90-80', '80;whoami', '-p 22'):
        with pytest.raises(ValueError): validate(dict(ports=invalid))
    with pytest.raises(ValueError): validate(dict(exclude_paths='https://other.invalid/'))
    assert restriction('nuclei', options)
    assert restriction('httpx', validate(), True)
    assert not restriction('zap', options, True)


def test_authenticated_crawl_honors_exclusions_and_never_saves_secret(website):
    origin, requests = website
    session = Session('cookie', 'session=PRIVATE-SESSION-TOKEN', label='test-account', verify_url=origin+'/private', marker='PRIVATE ACCOUNT PAGE')
    scan_id = engine.start(origin+'/private', [], True, True, profile='medium', options=dict(exclude_paths=['/excluded'], rate=100), session=session)
    scan = wait_scan(scan_id)
    assert scan['status'] == 'completed'
    assert scan['authentication']['verified']
    assert scan['coverage']['pages_checked'] >= 2
    assert not any(path == '/excluded' for path, auth in requests)
    assert any(path == '/allowed' and auth for path, auth in requests)
    encoded = json.dumps(scan)
    assert 'PRIVATE-SESSION-TOKEN' not in encoded
    assert 'Cookie' not in encoded
    assert 'PRIVATE ACCOUNT PAGE' not in encoded


def test_session_verification_rejects_invalid_public_and_cross_origin(website):
    origin, _ = website
    wrong = Session('cookie', 'session=wrong-secret', label='test', verify_url=origin+'/private', marker='PRIVATE ACCOUNT PAGE')
    with pytest.raises(ValueError, match='verification failed'): wrong.verify(origin, True)
    public = Session('bearer', 'token', label='test', verify_url=origin+'/', marker='Public login page')
    with pytest.raises(ValueError, match='also visible'): public.verify(origin, True)
    other = Session('bearer', 'token', label='test', verify_url='https://other.invalid/private', marker='private')
    with pytest.raises(ValueError, match='same origin'): other.verify(origin, True)
    with pytest.raises(ValueError): Session('cookie', 'header\r\ninjected')
    assert 'wrong-secret' not in json.dumps(wrong.redact({'error':'Cookie: session=wrong-secret'}))


def test_cross_tool_grouping_preserves_sources_and_keeps_distinct_targets():
    data = [finding('csp','https://example.com/','missing','low',tool='moth'),
            finding('Content Security Policy (CSP) Header Not Set','https://example.com/','rule 10038','medium',tool='zap'),
            finding('Content Security Policy header not observed','https://example.com/','template csp','info',tool='nuclei'),
            finding('csp','https://example.com/other','missing','low',tool='moth'),
            finding('XSS','https://example.com/','unrelated','high',tool='zap')]
    grouped = results.grouped(data)
    assert len(grouped) == 3
    assert grouped[0]['source_tools'] == ['moth', 'zap', 'nuclei']
    assert grouped[0]['severity'] == 'medium'
    assert len(grouped[0]['sources']) == 3
    assert grouped[0]['verification'] == 'observed-configuration'
    assert 'rule 10038' in grouped[0]['evidence']
    assert len(data) == 5 and 'sources' not in data[0]


def test_comparison_does_not_call_uncovered_or_failed_findings_resolved():
    old = dict(id='old', target='https://example.com/', profile='low', tools=[], status='completed', findings=[finding('csp','https://example.com/','missing')], steps=[dict(tool='moth',status='completed')], coverage=dict(checked_urls=['https://example.com/']))
    new = copy.deepcopy(old); new.update(id='new',findings=[])
    assert results.compare(new,old)['rows'][0]['status'] == 'resolved'
    new['coverage']['checked_urls'] = []
    assert results.compare(new,old)['rows'][0]['status'] == 'not_observed'
    new['status'] = 'partial'
    assert not results.compare(new,old)['comparable']
    new['status'] = 'completed'; new['authentication'] = dict(mode='cookie',label='another-user')
    assert results.compare(new,old)['rows'][0]['status'] == 'not_observed'


def test_skip_only_current_tool_continues_scan(monkeypatch):
    monkeypatch.setattr(engine, 'command', lambda tool: [tool])
    monkeypatch.setattr(engine, 'catalog', lambda: [])
    monkeypatch.setattr(engine, 'resolve', lambda *a: ['127.0.0.1'])
    monkeypatch.setattr(preflight, 'inspect', lambda *a: [])
    monkeypatch.setattr(engine, 'basic_profile', lambda *a: ([], {}))
    calls = []
    def run(tool, url, directory, cancel, *args, **kwargs):
        calls.append(tool)
        if tool == 'httpx':
            assert cancel.wait(5)
            raise adapters.Cancelled()
        return []
    monkeypatch.setattr(engine, 'run_tool', run)
    identifier = engine.start('https://example.com/', ['httpx', 'katana'], True)
    deadline = time.monotonic()+3
    while time.monotonic()<deadline:
        with engine.LOCK: active = engine.CURRENT.get(identifier)
        if active and active[0] == 'httpx': break
        time.sleep(.01)
    assert engine.skip_current(identifier)
    scan = wait_scan(identifier)
    assert calls == ['httpx', 'katana']
    assert scan['status'] == 'partial'
    assert next(s for s in scan['steps'] if s['tool']=='httpx')['status'] == 'skipped'
    assert next(s for s in scan['steps'] if s['tool']=='katana')['status'] == 'completed'
    assert not engine.skip_current(identifier)


def test_nmap_progress_uses_phase_percentage_not_fake_total(tmp_path):
    (tmp_path/'result.xml').write_text('<nmaprun><taskprogress task="Connect Scan" time="1" percent="42.25" remaining="12"/>')
    data = snapshot('nmap', tmp_path)
    assert data['phase'] == 'Connect Scan' and data['percent'] == 42.25
    assert data['last_activity']
    assert snapshot('katana', tmp_path)['percent'] is None
    with (tmp_path/'result.xml').open('a') as file:
        file.write('<taskbegin task="Service scan" time="2"/>')
    data = snapshot('nmap', tmp_path)
    assert data['phase'] == 'Service scan' and data['percent'] is None


def test_preflight_detects_empty_templates_and_cli_incompatibility(monkeypatch,tmp_path):
    monkeypatch.setattr(preflight,'TOOLS',tmp_path)
    monkeypatch.setattr(preflight.tools,'command',lambda tool: ['tool'])
    monkeypatch.setattr(preflight.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=b'-jsonl -dut',stderr=b''))
    rows=preflight.inspect('https://example.com/',['nuclei'],'high',validate())
    assert rows[0]['status']=='error' and 'empty' in rows[0]['message']
    folder=tmp_path/'nuclei/templates/http';folder.mkdir(parents=True)
    (folder/'one.yaml').write_text('id: example')
    assert preflight.inspect('https://example.com/',['nuclei'],'high',validate())[0]['status']=='ready'
    assert preflight.inspect('https://example.com/',['nmap'],'low',validate())[0]['status']=='error'


def test_execute_emits_live_progress_and_stays_cancellable(tmp_path):
    import sys
    cancel=threading.Event()
    counts=[]
    def update():
        counts.append(snapshot('test',tmp_path))
        cancel.set()
    with pytest.raises(adapters.Cancelled):
        adapters.execute([sys.executable,'-c','import time; print("working",flush=True); time.sleep(20)'],tmp_path,cancel,timeout=None,progress=update)
    assert counts and counts[0]['percent'] is None


def test_authenticated_zap_plan_and_katana_headers_are_origin_scoped(monkeypatch, tmp_path):
    import re
    from moth import zap_runtime
    monkeypatch.setattr(adapters,'command',lambda tool:[tool])
    monkeypatch.setattr(adapters,'resolve',lambda *a:['127.0.0.1'])
    monkeypatch.setattr(adapters,'parse',lambda *a:[])
    session=Session('cookie','session=PLAN-TEST-SECRET',label='qa',verify_url='https://example.com/private',marker='Private')
    plans=[]
    def run(cmd,url,directory,plan,cancel,progress): plans.append(plan)
    monkeypatch.setattr(zap_runtime,'run',run)
    options=validate(dict(exclude_paths=['/excluded'],rate=8,ports='443'))
    adapters.run_tool('zap','https://example.com/',tmp_path/'zap',threading.Event(),profile='medium',options=options,session=session)
    rule=plans[0]['jobs'][0]['rules'][0]
    assert rule['replacementString']=='session=PLAN-TEST-SECRET'
    assert re.fullmatch(rule['url'],'https://example.com/private/page')
    assert not re.fullmatch(rule['url'],'https://example.com.attacker.invalid/private')
    assert not re.fullmatch(rule['url'],'https://example.com:8443/private')
    spider=next(job for job in plans[0]['jobs'] if job['type']=='spider')
    assert not spider['parameters']['parseRobotsTxt'] and not spider['parameters']['parseSitemapXml']
    context=plans[0]['env']['contexts'][0]
    assert any(re.fullmatch(pattern,'https://example.com/excluded/child') for pattern in context['excludePaths'])
    calls=[]
    def execute(args,directory,cancel,**kwargs):
        path=Path(args[args.index('-H')+1])
        assert path.read_text()=='Cookie: session=PLAN-TEST-SECRET'
        assert 'PLAN-TEST-SECRET' not in ' '.join(args)
        calls.append(args)
        return ''
    monkeypatch.setattr(adapters,'execute',execute)
    adapters.run_tool('katana','https://example.com/',tmp_path/'katana',threading.Event(),profile='medium',options=options,session=session)
    assert calls[0][calls[0].index('-rl')+1]=='8'
    assert '-jc' in calls[0] and '-kf' not in calls[0]
    assert not list((tmp_path/'katana').rglob('session-headers.txt'))


def test_targeted_recheck_records_absence_without_rerunning_ultra_tools(monkeypatch):
    from moth.scan_options import validate
    original=dict(id='previous',created='2026-01-01T00:00:00+00:00',target='https://example.com/',profile='ultra',status='completed',tools=[],findings=[finding('csp','https://example.com/','missing')],steps=[],errors=[],coverage={},options=validate())
    storage.save(original)
    monkeypatch.setattr(engine,'resolve',lambda *a:['127.0.0.1'])
    monkeypatch.setattr(engine,'catalog',lambda:[])
    monkeypatch.setattr(preflight,'inspect',lambda *a:[])
    monkeypatch.setattr(engine,'basic_profile',lambda *a:([],dict(checked_urls=['https://example.com/'])))
    identifier=engine.start('https://example.com/',[],True,profile='ultra',active_authorized=True,recheck_of=dict(scan=original['id'],finding=original['findings'][0]['id']))
    scan=wait_scan(identifier)
    assert scan['tools']==[]
    assert scan['recheck_result']=='absent'
    assert not scan['comparison']['comparable']


@pytest.mark.parametrize('help_text,status', [
    ('SCAN TECHNIQUES:\n  -sS/sT/sA/sW/sM: TCP SYN/Connect scans\n  -oN/-oX/-oS/-oG <file>', 'ready'),
    ('  -sT: TCP Connect\n  -oX <file>', 'ready'),
    ('  -sS/sA/sW/sM: TCP scans\n  -oX <file>', 'error'),
    ('  -sS/sT/sA: TCP scans\n  -oN <file>', 'error'),
])
def test_nmap_preflight_understands_grouped_scan_flags(monkeypatch,help_text,status):
    monkeypatch.setattr(preflight.tools,'command',lambda tool:['nmap'])
    monkeypatch.setattr(preflight.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout=help_text.encode(),stderr=b''))
    assert preflight.inspect('https://example.com/',['nmap'],'low',validate())[0]['status']==status


@pytest.mark.parametrize('engine_code,engine_kind,image_code,expected', [
    (1,b'',0,'Docker engine is unavailable'),
    (0,b'windows\n',0,'Switch Docker Desktop to Linux containers'),
    (0,b'linux\n',1,'Repair ZAP image'),
    (0,b'linux\n',0,None),
])
def test_zap_preflight_distinguishes_engine_and_image_failures(monkeypatch,engine_code,engine_kind,image_code,expected):
    monkeypatch.setattr(preflight.tools,'command',lambda tool:['docker','ghcr.io/zaproxy/zaproxy@sha256:example'])
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=engine_code if args[1]=='info' else image_code,stdout=engine_kind,stderr=b'')
    monkeypatch.setattr(preflight.subprocess,'run',run)
    row=preflight.inspect('https://example.com/',['zap'],'low',validate())[0]
    if expected:
        assert row['status']=='error' and expected in row['message']
    else:assert row['status']=='ready'
    if engine_code or engine_kind.strip()!=b'linux':
        assert len(calls)==1


def test_preflight_failures_are_retained_as_tool_errors(monkeypatch):
    monkeypatch.setattr(engine,'command',lambda tool:[tool])
    monkeypatch.setattr(engine,'catalog',lambda:[])
    monkeypatch.setattr(engine,'resolve',lambda *args:['127.0.0.1'])
    diagnostics=[dict(tool='zap',status='error',message='Docker engine is unavailable.'),dict(tool='nuclei',status='error',message='Nuclei templates are missing.')]
    monkeypatch.setattr(preflight,'inspect',lambda *args:diagnostics)
    monkeypatch.setattr(engine,'basic_profile',lambda *args:pytest.fail('Scan began despite preflight failure'))
    identifier=engine.start('https://example.com/',['zap','nuclei'],True)
    scan=wait_scan(identifier)
    assert scan['status']=='failed'
    assert scan['errors']==[dict(tool=row['tool'],message=row['message']) for row in diagnostics]
    assert scan['preflight']==diagnostics and scan['steps']==[]
