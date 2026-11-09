"""Only tool-reported percentages are presented as progress."""
import re
from datetime import datetime, timezone


def snapshot(tool, directory):
    paths = [directory / 'stdout.log', directory / 'stderr.log']
    if tool == 'nmap':
        paths.append(directory / 'result.xml')
    size = 0
    modified = 0
    texts = []
    for path in paths:
        if path.exists():
            stat = path.stat()
            size += stat.st_size
            modified = max(modified, stat.st_mtime)
            with path.open('rb') as file:
                file.seek(max(0, stat.st_size - 32000))
                texts.append(file.read(32000).decode(errors='replace'))
    data = dict(phase='running', output_bytes=size, percent=None,
                last_activity=datetime.fromtimestamp(modified, timezone.utc).isoformat() if modified else None)
    if tool == 'nmap':
        text = '\n'.join(texts)
        matches = list(re.finditer(r'<taskprogress\b[^>]*task="([^"]+)"[^>]*percent="([\d.]+)"', text))
        if matches:
            data.update(phase=matches[-1][1], percent=min(100, max(0, float(matches[-1][2]))))
        else:
            matches = list(re.finditer(r'([^\r\n:]+) Timing: About ([\d.]+)% done', text))
            if matches:
                data.update(phase=matches[-1][1].strip(), percent=float(matches[-1][2]))
        beginnings = list(re.finditer(r'<taskbegin\b[^>]*task="([^"]+)"', text))
        progress_events = list(re.finditer(r'<taskprogress\b', text))
        if beginnings and (not progress_events or beginnings[-1].start() > progress_events[-1].start()):
            data.update(phase=beginnings[-1][1], percent=None)

    return data
