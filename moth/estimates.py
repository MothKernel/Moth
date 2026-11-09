"""Approximate remaining time, never an execution deadline."""
from datetime import datetime, timezone
from statistics import median
from .profiles import incompatibility

BASE = {'moth':(1,10),'httpx':(2,20),'sslyze':(20,120),'katana':(5,90),
        'zap':(20,180),'nuclei':(5,60),'retire':(5,60),'dnsx':(2,20),
        'wafw00f':(3,45),'subfinder':(15,180),'nmap':(2,30)}


def elapsed(started, now=None):
    try:
        start=datetime.fromisoformat(started)
        if start.tzinfo is None:
            start=start.replace(tzinfo=timezone.utc)
        return max(0,((now or datetime.now(timezone.utc))-start).total_seconds())
    except (TypeError,ValueError):
        return 0


def build(profile, target, stages, history, options=None, authenticated=False):
    factor={'low':1,'medium':2,'high':5,'ultra':12}[profile]
    estimates={}
    for tool in stages:
        from .scan_options import restriction
        if incompatibility(tool,target) or (options and restriction(tool,options,authenticated)):
            estimates[tool]=dict(low=0,high=0,source='skipped',samples=0)
            continue
        samples=[]
        for scan in history:
            # Older ZAP profiles could finish at a hard cap, so do not learn from those.
            if scan.get('profile')!=profile or not scan.get('duration_unlimited') or (options is not None and scan.get('options') != options):
                continue
            for step in scan.get('steps',[]):
                if step['tool']==tool and step['status']=='completed':
                    value=step.get('elapsed_seconds')
                    if isinstance(value,(int,float)) and value>0:
                        samples.append(value)
        if len(samples)>=3:
            center=median(samples)
            low,high=max(1,center*.6),max(2,center*1.6)
            source='history'
        else:
            low,high=BASE.get(tool,(5,120))
            low,high=low*factor,high*factor
            if tool=='nmap' and profile=='ultra':
                low,high=1500,7200
            elif tool in ('zap','nuclei') and profile=='ultra':
                low,high=600,5400
            if tool == 'nmap' and options:
                if options['ports']:
                    ports = set()
                    for part in options['ports'].split(','):
                        bounds = list(map(int, part.split('-')))
                        ports.update(range(bounds[0], bounds[-1] + 1))
                    minimum = len(ports) / options['nmap_rate']
                    low, high = max(1, minimum), max(10, minimum * 3 + (180 if profile != 'low' else 5))
                else:
                    low, high = low * 50 / options['nmap_rate'], high * 50 / options['nmap_rate']
            source='rough'
        estimates[tool]=dict(low=low,high=high,source=source,samples=len(samples))
    return estimates


def remaining(scan, now=None):
    budgets=scan.get('estimates',{})
    steps={s['tool']:s for s in scan.get('steps',[])}
    low=high=0
    current=None
    unknown=False
    for tool in ['moth']+scan.get('tools',[]):
        step=steps.get(tool,{})
        if step.get('status') in ('completed','failed','skipped','cancelled'):
            continue
        estimate=budgets.get(tool)
        if estimate is None:
            unknown=True
            continue
        used=elapsed(step.get('started'),now) if step.get('status')=='running' else 0
        overdue=used>=estimate['high'] and estimate['high']>0
        left=(max(0,estimate['low']-used),max(0,estimate['high']-used))
        if step.get('status')=='running':
            current=dict(tool=tool,elapsed=used,low=left[0],high=left[1],unknown=overdue,source=estimate['source'])
        unknown=unknown or overdue
        low+=left[0]; high+=left[1]
    return dict(low=low,high=high,unknown=unknown,current=current,elapsed=elapsed(scan.get('created'),now))


def duration(seconds):
    seconds=max(0,int(seconds))
    if seconds<60:
        return f'{seconds}s'
    minutes=round(seconds/60)
    if minutes<60:
        return f'{minutes} min'
    hours,minutes=divmod(minutes,60)
    return f'{hours}h {minutes:02d} min'


def recorded_time(scan):
    if scan.get('finished'):
        try:
            return elapsed(scan.get('created'), datetime.fromisoformat(scan['finished']))
        except (TypeError,ValueError):
            pass
    values=[step['elapsed_seconds'] for step in scan.get('steps',[]) if 'elapsed_seconds' in step]
    return sum(values) if values else None
