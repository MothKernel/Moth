"""Conservative cross-tool grouping, comparisons and actionable priorities."""
import copy
from .targets import normalize

SEVERITY = {'critical': 5, 'high': 4, 'medium': 3, 'low': 2, 'info': 1}
ALIASES = {
 'csp': {'csp', 'content security policy (csp) header not set', 'content security policy header not observed', 'content-security-policy header is missing', 'no enforced content security policy was observed'},
 'nosniff': {'nosniff', 'x-content-type-options header not observed', 'x-content-type-options header missing'},
 'frame': {'frame', 'x-frame-options header not observed', 'x-frame-options header not set'},
 'hsts': {'hsts', 'strict-transport-security header not set', 'strict-transport-security header not observed'},
}


def identity(item):
    code = item['code'].strip().casefold()
    canonical = next((name for name, names in ALIASES.items() if code in names), None)
    # Unknown rules are kept separate; do not merge XSS/CSRF just because their names resemble each other.
    key = canonical or item['tool'] + ':' + code
    if canonical is None:
        key += ':' + item.get('evidence', '')
    try:
        target = normalize(item['target'])
    except ValueError:
        target = item['target']  # Credentials may have been replaced in a sensitive URL path/host.
    return target, key


def grouped(findings):
    groups = {}
    for original in findings:
        key = identity(original)
        if key not in groups:
            item = copy.deepcopy(original)
            item['sources'] = []
            item['verification'] = 'observed-configuration' if original['tool'] == 'moth' else 'manual-review'
            groups[key] = item
        item = groups[key]
        if original['tool'] == 'moth':
            item['text'], item['code'] = copy.deepcopy(original['text']), original['code']
            item['verification'] = 'observed-configuration'
        if SEVERITY.get(original['severity'], 0) > SEVERITY.get(item['severity'], 0):
            item['severity'] = original['severity']
        source = {k: copy.deepcopy(original.get(k, '')) for k in ('id', 'tool', 'code', 'evidence', 'technical', 'confidence')}
        if source not in item['sources']:
            item['sources'].append(source)
        item['source_tools'] = list(dict.fromkeys(s['tool'] for s in item['sources']))
        item['evidence'] = '\n\n'.join(s['tool'] + ': ' + s['evidence'] for s in item['sources'])[:20000]
    return list(groups.values())


def context(scan):
    return {key: scan.get(key) for key in ('target', 'profile', 'options', 'tools', 'allow_private', 'authentication', 'tool_versions', 'recheck_of')}


def compare(current, previous):
    if not previous:
        return dict(baseline=None, comparable=False, reason='no_baseline', rows=[])
    comparable = context(current) == context(previous) and current['status'] == 'completed' and previous['status'] == 'completed'
    before = {identity(x): x for x in grouped(previous['findings'])}
    after = {identity(x): x for x in grouped(current['findings'])}
    rows = []
    for key in sorted(before.keys() | after.keys()):
        status = 'persistent' if key in before and key in after else ('new' if key in after else 'resolved') if comparable else ('new_observation' if key in after else 'not_observed')
        if status == 'resolved':
            old = before[key]
            completed = {step['tool'] for step in current.get('steps', []) if step['status'] == 'completed'}
            visited = current.get('coverage', {}).get('checked_urls', [])
            if not set(old['source_tools']).issubset(completed) or ('moth' in old['source_tools'] and old['target'] not in visited):
                status = 'not_observed'
        rows.append(dict(status=status, finding=after.get(key, before.get(key))))
    return dict(baseline=previous['id'], comparable=comparable, reason='same_scope' if comparable else 'different_or_incomplete_scope', rows=rows)


def priorities(scan):
    return sorted(grouped(scan.get('findings', [])), key=lambda x: (-SEVERITY.get(x['severity'], 0), x['kind'] == 'information', x['target']))
