"""Explicit, bounded scan profiles. They change coverage, not just UI labels."""
import ipaddress
from urllib.parse import urlsplit

PROFILES = {
    'low': dict(pages=1, depth=1, js=False, scripts=5, rate=2,
                spider=False, active=False, ports='target', templates='csp', dns='basic'),
    'medium': dict(pages=5, depth=3, js=True, scripts=15, rate=3,
                   spider=True, active=False, ports='target', templates='bundled', dns='extended'),
    'high': dict(pages=20, depth=5, js=True, scripts=30, rate=5,
                 spider=True, active=True, ports='common', templates='focused', dns='extended'),
    'ultra': dict(pages=100, depth=10, js=True, scripts=100, rate=10,
                  spider=True, active=True, ports='all', templates='http', dns='all_records'),
}


def get_profile(name):
    if name not in PROFILES:
        raise ValueError('Unknown scan level. Choose Low, Medium, High or Ultra.')
    return dict(PROFILES[name])


def incompatibility(tool, url):
    host = urlsplit(url).hostname
    if tool == 'sslyze' and urlsplit(url).scheme != 'https':
        return 'SSLyze requires HTTPS; no encrypted connection exists at this HTTP URL.'
    if tool in ('dnsx', 'subfinder'):
        try:
            ipaddress.ip_address(host)
            return 'DNS/subdomain discovery needs a domain name, not an IP address.'
        except ValueError:
            if tool == 'subfinder' and '.' not in host:
                return 'Passive subdomain discovery needs a domain name, not a local hostname.'
    return ''


def scope(tool, name):
    p = get_profile(name)
    scopes = {
        'moth': f"Up to {p['pages']} same-origin pages; headers, cookies and TLS certificate. No redirects.",
        'httpx': 'HTTP status, title and technologies' + ('; content type, length, IP, HTTP/2 and TLS probes.' if name != 'low' else '.'),
        'katana': f"Same-origin crawl: depth {p['depth']}, no duration cap, JavaScript parsing: {p['js']}.",
        'nuclei': {'csp':'Bundled CSP check.', 'bundled':'Bundled header checks.', 'focused':'Signed HTTP templates: technology, exposures and misconfigurations.', 'http':'Standard signed HTTP templates; no OAST, DoS, fuzzing, brute-force, code or browser templates.'}[p['templates']],
        'zap': f"Passive rules; spider: {p['spider']}; active scanning: {p['active']}. No duration cap. Exact-origin context.",
        'retire': f"Analyze inline scripts and up to {p['scripts']} same-origin script files for known library advisories.",
        'nmap': {'target':'Selected website TCP port.', 'common':'33 common TCP ports plus the selected port on the same server.', 'all':'All 65,535 TCP ports on the same server.'}[p['ports']] + (' Service detection and selected web/TLS NSE checks.' if name in ('high','ultra') else ' Service detection.' if name == 'medium' else ''),
        'sslyze': 'TLS certificate and supported protocol/cipher checks.' + (' Plus compression, fallback, renegotiation and available vulnerability checks.' if name in ('high','ultra') else ''),
        'wafw00f': 'Web application firewall detection.' + (' Test all available WAF signatures.' if name in ('high','ultra') else ''),
        'dnsx': 'DNS records: ' + {'basic':'A, AAAA, CNAME.', 'extended':'A, AAAA, CNAME, MX, NS, TXT, SOA.', 'all_records':'A, AAAA, CNAME, MX, NS, TXT, SOA, SRV, PTR, CAA, zone-transfer check.'}[p['dns']],
        'subfinder': "Passive discovery without an overall duration cap." + (' All available sources; API-key sources require separate configuration.' if name in ('high','ultra') else ''),
    }
    return scopes.get(tool, '')
