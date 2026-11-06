from datetime import datetime,timezone
from moth import estimates


def test_estimate_uses_history_without_treating_it_as_a_limit():
    history=[dict(profile='low',duration_unlimited=True,steps=[dict(tool='httpx',status='completed',elapsed_seconds=s)]) for s in (10,20,30)]
    result=estimates.build('low','https://example.com',['httpx','sslyze'],history)
    assert result['httpx']['source']=='history' and result['httpx']['samples']==3
    assert result['httpx']['low']==12 and result['httpx']['high']==32
    old=[dict(profile='low',steps=[dict(tool='httpx',status='completed',elapsed_seconds=1)])]*5
    assert estimates.build('low','https://example.com',['httpx'],old)['httpx']['source']=='rough'


def test_overdue_estimate_is_unknown_not_zero_or_a_reset_countdown():
    scan=dict(created='2026-01-01T00:00:00+00:00',tools=['httpx'],steps=[dict(tool='moth',status='completed'),dict(tool='httpx',status='running',started='2026-01-01T00:00:00+00:00')],estimates={'httpx':dict(low=5,high=20,source='rough')})
    result=estimates.remaining(scan,datetime(2026,1,1,0,1,tzinfo=timezone.utc))
    assert result['unknown'] and result['current']['unknown']
    assert result['current']['elapsed']==60


def test_incompatible_tools_do_not_inflate_total():
    result=estimates.build('ultra','http://127.0.0.1',['sslyze','dnsx'],[])
    assert all(e['high']==0 and e['source']=='skipped' for e in result.values())
