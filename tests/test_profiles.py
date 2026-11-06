import json
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from moth import profiles, engine, adapters, tools, storage


def test_levels_increase_real_limits():
    for key in ('pages','depth','scripts','rate'):
        values=[profiles.get_profile(level)[key] for level in profiles.PROFILES]
        assert values==sorted(set(values))
    assert profiles.get_profile('high')['active'] and profiles.get_profile('ultra')['active']
    assert profiles.incompatibility('sslyze','http://127.0.0.1:3000')
    assert profiles.incompatibility('dnsx','https://127.0.0.1')
    assert not profiles.incompatibility('nmap','http://127.0.0.1:3000')


def test_profile_validation_and_ultra_missing_tools(monkeypatch):
    with pytest.raises(ValueError,match='Unknown scan level'):
        engine.start('https://example.com',[],True,profile='unknown')
    with pytest.raises(ValueError,match='active checks'):
        engine.start('https://example.com',[],True,profile='high')
    monkeypatch.setattr(engine,'command',lambda tool: None)
    monkeypatch.setattr(engine,'catalog',lambda:[])
    with pytest.raises(ValueError,match='not installed'):
        engine.start('http://127.0.0.1',[],True,True,profile='ultra',active_authorized=True)


@pytest.mark.parametrize('tool',['httpx','katana','nuclei','dnsx','subfinder','sslyze','wafw00f','nmap','zap'])
@pytest.mark.parametrize('profile',list(profiles.PROFILES))
def test_all_profile_commands_and_zap_plans(monkeypatch,tmp_path,tool,profile):
    monkeypatch.setattr(adapters,'command',lambda tool:['tool-'+tool])
    monkeypatch.setattr(adapters,'resolve',lambda *args:['203.0.113.1'])
    monkeypatch.setattr(tools,'TOOLS',tmp_path/'managed')
    # run_tool imports the configurable root from config for template preparation.
    from moth import config
    monkeypatch.setattr(config,'TOOLS',tmp_path/'managed')
    (tmp_path/'managed/nuclei/templates/http').mkdir(parents=True)
    calls=[]
    plans=[]
    def execute(args,directory,cancel,**kwargs):
        calls.append((args,kwargs))
        if tool=='zap':
            plans.append(json.loads((directory/'plan.yaml').read_text()))
        return ''
    monkeypatch.setattr(adapters,'execute',execute)
    from moth import zap_runtime
    def run_zap(cmd,url,directory,plan,cancel,progress=None):
        plans.append(plan)
        calls.append((cmd,dict(timeout=None)))
    monkeypatch.setattr(zap_runtime,'run',run_zap)
    monkeypatch.setattr(adapters,'parse',lambda *args:[])
    adapters.run_tool(tool,'https://example.com:8443/',tmp_path/tool,threading.Event(),profile=profile)
    args,kwargs=calls[-1]
    p=profiles.get_profile(profile)
    assert kwargs['timeout'] is None
    assert '-ct' not in args and '--host-timeout' not in args and '--script-timeout' not in args
    if tool=='subfinder':
        assert int(args[args.index('-max-time')+1])>=100000000
    if tool=='katana':
        assert args[args.index('-d')+1]==str(p['depth'])
        assert ('-jc' in args)==p['js']
    if tool=='nuclei':
        assert ('-dut' in args)==(profile in ('high','ultra'))
        if profile=='ultra':
            assert '-tags' not in args and '-ni' in args and '-pt' in args
    if tool=='nmap':
        ports=args[args.index('-p')+1]
        assert ports==('1-65535' if profile=='ultra' else ports)
        assert '8443' in ports or profile=='ultra'
        assert ('--script' in args)==(profile in ('high','ultra'))
        assert '203.0.113.1'==args[-1]
    if tool=='zap':
        jobs=plans[0]['jobs']
        types=[job['type'] for job in jobs]
        assert ('activeScan' in types)==p['active']
        assert ('spider' in types)==p['spider']
        assert 'includePaths' in plans[0]['env']['contexts'][0]
        for job in jobs:
            params=job.get('parameters',{})
            if 'maxDuration' in params: assert params['maxDuration']==0
            if 'maxRuleDurationInMins' in params: assert params['maxRuleDurationInMins']==0
        if p['active']:
            active=next(job for job in jobs if job['type']=='activeScan')
            assert active['parameters']['maxScanDurationInMins']==0
            assert active['policyDefinition']['defaultStrength']==('High' if profile=='ultra' else 'Medium')


def test_builtin_profile_crawls_within_origin_and_records_limits():
    class Handler(BaseHTTPRequestHandler):
        requests=[]
        def do_GET(self):
            self.requests.append(self.path)
            self.send_response(200)
            self.send_header('Content-Type','text/html')
            self.end_headers()
            links=''.join(f'<a href="/page{i}">x</a>' for i in range(12))
            self.wfile.write((links+'<a href="https://outside.invalid/">no</a><a href="/logout">no</a>').encode())
        def log_message(self,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        url=f'http://127.0.0.1:{server.server_port}/'
        identifier=engine.start(url,[],True,True,profile='medium')
        deadline=time.monotonic()+10
        while identifier in engine.ACTIVE and time.monotonic()<deadline:
            time.sleep(.02)
        result=storage.get(identifier)
        assert result['status']=='completed'
        assert result['profile']=='medium'
        assert result['coverage']['pages_checked']==5
        assert result['coverage']['limit_reached']
        assert len(Handler.requests)==5
        assert '/logout' not in Handler.requests
        assert len({f['target'] for f in result['findings']})==5
    finally:
        server.shutdown()
        server.server_close()


def test_retire_profile_expands_same_origin_script_coverage(monkeypatch,tmp_path):
    monkeypatch.setattr(adapters,'command',lambda tool:['retire'])
    monkeypatch.setattr(adapters,'resolve',lambda *args:['127.0.0.1'])
    requests=[]
    def fetch(url,*args):
        requests.append(url)
        body=''.join(f'<script src="/s{i}.js"></script>' for i in range(20)) if url.endswith('/') else 'var app=1;'
        return 200,[],body.encode(),None
    monkeypatch.setattr(adapters,'fetch',fetch)
    monkeypatch.setattr(adapters,'execute',lambda *a,**k:'')
    monkeypatch.setattr(adapters,'parse',lambda *a:[])
    adapters.run_tool('retire','http://127.0.0.1/',tmp_path/'retire',threading.Event(),True,profile='medium')
    assert len(requests)==16


def test_ultra_selects_all_integrations_and_records_incompatible_skips(monkeypatch):
    monkeypatch.setattr(engine,'command',lambda tool:[tool])
    monkeypatch.setattr(engine,'catalog',lambda:[dict(id=t['id'],status='ready',version='1') for t in tools.REGISTRY])
    monkeypatch.setattr(engine,'resolve',lambda *args:['127.0.0.1'])
    monkeypatch.setattr(engine,'basic_profile',lambda *args:([],{}))
    calls=[]
    def run_tool(tool,*args,profile,progress=None):
        calls.append((tool,profile))
        return []
    monkeypatch.setattr(engine,'run_tool',run_tool)
    identifier=engine.start('http://127.0.0.1:3000',[],True,True,profile='ultra',active_authorized=True)
    deadline=time.monotonic()+5
    while identifier in engine.ACTIVE and time.monotonic()<deadline:
        time.sleep(.01)
    scan=storage.get(identifier)
    assert scan['status']=='completed'
    assert len(scan['tools'])==10
    assert all(profile=='ultra' for tool,profile in calls)
    skipped={s['tool'] for s in scan['steps'] if s['status']=='skipped'}
    assert skipped=={'sslyze','dnsx','subfinder'}
    assert all(s['reason'] for s in scan['steps'] if s['status']=='skipped')
    assert '65,535' in scan['tool_scope']['nmap']


def test_high_prepares_templates_in_moth_directory(monkeypatch,tmp_path):
    from moth import config
    monkeypatch.setattr(config,'TOOLS',tmp_path/'managed')
    monkeypatch.setattr(adapters,'command',lambda tool:['nuclei'])
    monkeypatch.setattr(adapters,'resolve',lambda *args:['203.0.113.1'])
    calls=[]
    def execute(args,*rest,**kwargs):
        calls.append(args)
        if '-ut' in args:
            folder=Path(args[args.index('-ud')+1])
            (folder/'http').mkdir(parents=True)
        return ''
    monkeypatch.setattr(adapters,'execute',execute)
    adapters.run_tool('nuclei','https://example.com',tmp_path/'run',threading.Event(),profile='high')
    assert len(calls)==2 and '-ut' in calls[0]
    assert '-dut' in calls[1] and '-tags' in calls[1]


def test_nmap_timeout_is_not_reported_as_complete(tmp_path):
    (tmp_path/'result.xml').write_text('<nmaprun><host timedout="true"/></nmaprun>')
    with pytest.raises(ValueError,match='incomplete'):
        adapters.parse('nmap','https://example.com','',tmp_path)
