"""Strict target parsing and bounded, DNS-pinned HTTP requests."""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import quote, urlsplit, urlunsplit


def normalize(value):
    value = value.strip()
    if not value or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise ValueError("Enter a valid website URL without spaces or control characters.")
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Only HTTP(S) URLs without embedded credentials are supported.")
    host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if len(host) > 253:
        raise ValueError("Hostname is too long.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or any(
            not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
            for label in host.split(".")
        ):
            raise ValueError("Invalid hostname.")
    port = parts.port  # validates range
    if port == 0:
        raise ValueError("Port zero is not supported.")
    authority = f"[{host}]" if ":" in host else host
    if port:
        authority += f":{port}"
    # Queries may contain tokens and are deliberately excluded from this public assessment.
    path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
    return urlunsplit((parts.scheme, authority, path, "", ""))


def resolve(url, allow_private=False):
    p = urlsplit(url)
    addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(
        p.hostname, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)))
    if not addresses:
        raise ValueError("The hostname did not resolve.")
    if not allow_private and any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Private/local addresses require the local laboratory option.")
    return addresses


def fetch(url, allow_private=False, max_bytes=512_000, headers=None):
    """One GET only. No proxy environment, no redirects, no unverified TLS fallback."""
    p = urlsplit(url)
    addresses = resolve(url, allow_private)
    cls = http.client.HTTPSConnection if p.scheme == "https" else http.client.HTTPConnection
    connection = cls(p.hostname, p.port, timeout=10)

    def pinned_connection(address, timeout=10, source_address=None, **kwargs):
        return socket.create_connection((addresses[0], address[1]), timeout, source_address)

    connection._create_connection = pinned_connection
    try:
        connection.request("GET", p.path or "/", headers={
            "User-Agent": "Moth/0.2 (authorized website assessment)", "Accept": "text/html,*/*;q=0.5", **(headers or {})
        })
        cert = connection.sock.getpeercert() if connection.sock and p.scheme == "https" else None
        response = connection.getresponse()
        headers = response.getheaders()
        chunks = []
        remaining = max_bytes
        deadline = time.monotonic() + 15
        while remaining > 0:
            if time.monotonic() > deadline:
                raise TimeoutError("Response exceeded the read time limit.")
            chunk = response.read1(min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return response.status, headers, b"".join(chunks), cert
    finally:
        connection.close()
