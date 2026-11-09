"""Ephemeral credentials; no credentials are part of persisted scan configuration."""
import base64
import re
from .targets import normalize, fetch


class Session:
    def __init__(self, mode='none', value='', username='', password='', label='', verify_url='', marker=''):
        if mode not in ('none', 'cookie', 'bearer', 'basic'):
            raise ValueError('Unknown authentication mode.')
        for text in (value, username, password, label, marker):
            if len(text) > 16000 or any(ord(c) < 32 for c in text):
                raise ValueError('Session fields cannot contain control characters and must be shorter than 16000 characters.')
        self.mode, self.label = mode, label.strip()
        self.verify_url = normalize(verify_url) if verify_url.strip() else ''
        self.marker = marker
        self.headers = {}
        self.secrets = []
        if mode == 'basic':
            if ':' in username:
                raise ValueError('HTTP Basic usernames cannot contain a colon.')
            if not username or not password:
                raise ValueError('Enter the HTTP Basic username and password.')
            value = 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()
            self.headers = {'Authorization': value}
            self.secrets = [password, value, value.split(' ', 1)[1]]
        elif mode != 'none':
            if not value.strip():
                raise ValueError('Enter a session cookie or Bearer token.')
            self.headers = {'Cookie' if mode == 'cookie' else 'Authorization': value if mode == 'cookie' else 'Bearer ' + value}
            self.secrets = [value] + list(self.headers.values())
            if mode == 'cookie':
                self.secrets += [x.split('=', 1)[1].strip() for x in value.split(';') if '=' in x]
        if mode != 'none' and (not self.label or not self.verify_url or not marker):
            raise ValueError('Authenticated assessments need a non-secret account label, verification URL and text visible only after login.')
        if any(secret and secret in self.label for secret in self.secrets):
            raise ValueError('The account label must not contain a credential.')

    def public(self):
        return dict(mode=self.mode, label=self.label, verified=False)

    def redact(self, value):
        if isinstance(value, str):
            for secret in sorted(set(self.secrets), key=len, reverse=True):
                if secret:
                    value = value.replace(secret, '[REDACTED]') if len(secret) >= 4 else re.sub(r'(?<![A-Za-z0-9])' + re.escape(secret) + r'(?![A-Za-z0-9])', '[REDACTED]', value)
            return value
        if isinstance(value, dict):
            return {k: v if k in ('status', 'tool', 'mode', 'severity', 'kind', 'confidence', 'phase', 'verification', 'source_language') else self.redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        return value

    def verify(self, target, allow_private=False):
        if not self.headers:
            return None
        from urllib.parse import urlsplit
        if urlsplit(self.verify_url)[:2] != urlsplit(target)[:2]:
            raise ValueError('The session verification URL must have the same origin as the assessment.')
        status, _, body, _ = fetch(self.verify_url, allow_private, headers=self.headers)
        if not 200 <= status < 300 or self.marker not in body.decode('utf-8', 'replace'):
            raise ValueError('Session verification failed: the authenticated response did not contain the expected text. Refresh the session or verification settings.')
        # A public marker must not be accepted as proof of authenticated access.
        public_status, _, public_body, _ = fetch(self.verify_url, allow_private)
        if 200 <= public_status < 300 and self.marker in public_body.decode('utf-8', 'replace'):
            raise ValueError('The verification text is also visible without credentials. Choose text from a private page.')
        return dict(mode=self.mode, label=self.label, verified=True)
