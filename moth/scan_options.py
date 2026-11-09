"""Validated scope controls, independent from scan depth."""
import re
from urllib.parse import urlsplit, unquote
from .targets import normalize

DEFAULT_EXCLUSIONS = []


def validate(value=None):
    value = value or {}
    exclusions = value.get('exclude_paths', DEFAULT_EXCLUSIONS)
    if isinstance(exclusions, str):
        exclusions = exclusions.splitlines()
    cleaned = []
    for path in exclusions:
        path = path.strip()
        if not path:
            continue
        if not path.startswith('/') or '?' in path or '#' in path or len(path) > 500 or any(ord(c) < 32 for c in path):
            raise ValueError('Excluded paths must start with / and contain no query strings or control characters.')
        cleaned.append(path.rstrip('/') or '/')
    if len(cleaned) > 100:
        raise ValueError('Use at most 100 excluded path prefixes.')
    rate = int(value.get('rate', 2))
    nmap_rate = int(value.get('nmap_rate', 50))
    if not 1 <= rate <= 100 or not 1 <= nmap_rate <= 5000:
        raise ValueError('Web rate must be 1–100 requests/s; Nmap rate must be 1–5000 probes/s.')
    ports = str(value.get('ports', '')).strip()
    if ports:
        for part in ports.split(','):
            if not re.fullmatch(r'\d+(?:-\d+)?', part):
                raise ValueError('Ports must be comma-separated numbers or ranges, for example 80,443,8000-8010.')
            ends = list(map(int, part.split('-')))
            if any(not 1 <= n <= 65535 for n in ends) or ends[0] > ends[-1]:
                raise ValueError('Port ranges must be ascending and within 1–65535.')
    return dict(exclude_paths=list(dict.fromkeys(cleaned)), rate=rate, nmap_rate=nmap_rate, ports=ports)


def excluded(url, options):
    path = unquote(urlsplit(normalize(url)).path).casefold()
    return any(path == p.casefold() or path.startswith(p.casefold().rstrip('/') + '/') for p in options['exclude_paths'])


def exclusion_regexes(url, options):
    p = urlsplit(url)
    origin = re.escape(f'{p.scheme}://{p.netloc}')
    return ['(?i)^' + origin + re.escape(path) + r'(?:[/?].*)?$' for path in options['exclude_paths']]


def restriction(tool, options, authenticated=False):
    # These adapters cannot enforce arbitrary path exclusions on their own probes.
    if options['exclude_paths'] != DEFAULT_EXCLUSIONS and tool in ('nuclei', 'wafw00f'):
        return 'Skipped: this adapter cannot enforce custom excluded paths. Use the built-in checker, Retire.js, Katana or ZAP for this scope.'
    if authenticated and tool in ('httpx', 'nuclei', 'wafw00f'):
        return 'Skipped: this adapter does not forward the protected session. Authenticated checks use Moth, Retire.js, Katana and ZAP; network/DNS checks need no session.'
    return ''
