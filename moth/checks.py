import ssl
import re
import time
from http.cookies import SimpleCookie, CookieError
from urllib.parse import urlsplit
from .findings import finding
from .targets import fetch


def basic(url, allow_private=False):
    results = []
    if urlsplit(url).scheme == "http":
        results.append(finding("http", url, "URL scheme: http", "medium", "configuration"))
    try:
        status, raw_headers, _, cert = fetch(url, allow_private)
    except ssl.SSLCertVerificationError as exc:
        results.append(finding("certificate", url, str(exc), "medium", "configuration"))
        return results, {"coverage": "TLS handshake only; page not retrieved", "http_status": None}
    headers = {k.lower(): v for k, v in raw_headers}
    if 300 <= status < 400:
        # Do not echo Location: it may contain authentication tokens.
        results.append(finding("redirect", url, f"HTTP {status}; destination omitted", "info", "information"))
    is_html = "text/html" in headers.get("content-type", "").lower()
    if is_html:
        csp = headers.get("content-security-policy", "")
        if not csp:
            results.append(finding("csp", url, "Content-Security-Policy header absent"))
        frame_option = headers.get("x-frame-options", "").strip().lower()
        if "frame-ancestors" not in csp.lower() and frame_option not in ("deny", "sameorigin"):
            results.append(finding("frame", url, "No frame-ancestors directive or valid X-Frame-Options"))
    hsts = headers.get("strict-transport-security", "")
    max_age = re.search(r"(?:^|;)\s*max-age\s*=\s*(\d+)\s*(?:;|$)", hsts, re.I)
    if urlsplit(url).scheme == "https" and (not max_age or int(max_age[1]) <= 0):
        results.append(finding("hsts", url, "Strict-Transport-Security absent, invalid, or max-age is zero"))
    if headers.get("x-content-type-options", "").strip().lower() != "nosniff":
        results.append(finding("nosniff", url, "X-Content-Type-Options is not nosniff"))
    cookie_count = 0
    for name, value in raw_headers:
        if name.lower() != "set-cookie":
            continue
        parsed = SimpleCookie()
        try:
            parsed.load(value)
        except CookieError:
            continue
        for cookie in parsed.values():
            cookie_count += 1
            for attr, code in (("secure", "cookie_secure"), ("httponly", "cookie_httponly"), ("samesite", "cookie_samesite")):
                if not cookie[attr]:
                    results.append(finding(code, url, f"Cookie {cookie.key[:80]}: {attr} absent; value redacted",
                                           "low" if attr == "secure" else "info", "review"))
    coverage = {"http_status": status, "coverage": "One GET, initial response only; no redirects followed",
                "cookie_count": cookie_count, "tls_verified": urlsplit(url).scheme == "https"}
    if cert and cert.get("notAfter"):
        remaining = int((ssl.cert_time_to_seconds(cert["notAfter"]) - time.time()) / 86400)
        coverage["certificate_days_remaining"] = remaining
        if remaining < 30:
            results.append(finding("certificate_expiring", url, f"Certificate validity remaining: {remaining} days", "low", "review"))
    return results, coverage
