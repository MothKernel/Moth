import threading
import pytest
from moth import zap_runtime,adapters


class SpiderClient:
    def call(self,component,kind,name,**params):
        if name=='scans':
            return {'scans':[dict(id='0',progress='100',state='FINISHED')]}
        if name=='fullResults':
            return {'fullResults':[{'urlsInScope':[
                dict(url='https://example.com/page?token=SECRET',processed='true',statusCode='200',messageId='1'),
                dict(url='https://example.com/app.js',processed='true',statusCode='200',messageId='2'),
                dict(url='https://outside.invalid/',processed='true',messageId='3')]}]}
        if name=='message':
            return {'message':{'responseHeader':'HTTP/1.1 200 OK\r\nContent-Type: '+('text/html' if params['id']=='1' else 'application/javascript')+'\r\n', 'responseBody':'NEVER-STORE-BODY'}}
        raise AssertionError(name)


def test_spider_counts_confirmed_pages_and_resources_without_leaking_queries():
    result=zap_runtime.spider_snapshot(SpiderClient(),'https://example.com/',headers=True)
    assert result['status']=='completed'
    assert result['visited_urls']==2 and result['html_pages']==1
    assert result['html_count_complete']
    assert 'SECRET' not in str(result) and 'NEVER-STORE-BODY' not in str(result)
    assert len(result['urls'])==2


def test_spider_metadata_collection_can_be_cancelled():
    cancel=threading.Event(); cancel.set()
    with pytest.raises(adapters.Cancelled):
        zap_runtime.spider_snapshot(SpiderClient(),'https://example.com/',headers=True,cancel=cancel)


def test_daemon_is_shut_down_when_user_stops(monkeypatch,tmp_path):
    cancel=threading.Event()
    calls=[]
    class Client:
        def __init__(self,*args): pass
        def call(self,component,kind,name,**params):
            calls.append(name)
            if name=='version': return {'version':'2.17.0'}
            if name=='runPlan':
                cancel.set()
                return {'planId':'0'}
            if name=='shutdown': return {'Result':'OK'}
            raise AssertionError(name)
    class Process:
        pid=123
        def poll(self): return None
        def wait(self,timeout=None): return 0
    monkeypatch.setattr(zap_runtime,'Client',Client)
    monkeypatch.setattr(zap_runtime.subprocess,'Popen',lambda *a,**k:Process())
    events=[]
    with pytest.raises(adapters.Cancelled):
        zap_runtime.run(['native-zap'],'https://example.com',tmp_path,dict(jobs=[dict(type='spider')]),cancel,events.append)
    assert 'shutdown' in calls
    assert events[-1]['spider']['status']=='cancelled'
