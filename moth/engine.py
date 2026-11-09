import json
import threading
import uuid
import time
from collections import deque
from .profiles import get_profile, incompatibility, scope
from . import estimates
from . import storage, preflight
from .scan_options import validate as validate_options, excluded, restriction
from .session import Session
from .results import compare, priorities, context, grouped
from .adapters import Cancelled, run_tool
from .checks import basic
from .config import RUNS
from .targets import normalize, resolve
from .tools import command, metadata, catalog

LOCK = threading.Lock()
ACTIVE = {}
CURRENT = {}


class ToolCancel:
    def __init__(self, scan_stop, tool_skip):
        self.scan_stop, self.tool_skip = scan_stop, tool_skip

    def is_set(self):
        return self.scan_stop.is_set() or self.tool_skip.is_set()

    def wait(self, seconds):
        until = time.monotonic() + seconds
        while not self.is_set():
            remaining = until - time.monotonic()
            if remaining <= 0:
                return False
            self.tool_skip.wait(min(.05, remaining))
        return True


def skip_current(scan_id):
    with LOCK:
        current = CURRENT.get(scan_id)
        if current:
            current[1].set()
            return True
    return False


def start(target, selected, authorized, allow_private=False, profile="low", active_authorized=False, options=None, session=None, recheck_of=None):
    if not authorized:
        raise ValueError("Confirm that you have permission to assess this target.")
    settings = get_profile(profile)
    options = validate_options(options)
    session = session or Session()
    if profile in ("high", "ultra") and not active_authorized:
        raise ValueError("Confirm permission for active checks and additional server ports before using High or Ultra.")
    url = normalize(target)
    if profile == "ultra" and not recheck_of:
        from .tools import REGISTRY
        selected = [tool["id"] for tool in REGISTRY]
    if excluded(url, options):
        raise ValueError("The starting URL is excluded by your scope settings.")
    # Network resolution belongs in the worker; the UI stays responsive.
    selected = list(dict.fromkeys(selected))
    if len(selected) > 10 or any(not metadata(tool) for tool in selected):
        raise ValueError("Unknown tool selection.")
    installed = catalog()
    if any(tool["id"] in selected and tool["status"] in ("queued", "installing") for tool in installed):
        raise ValueError("Wait for the selected tools to finish installing or updating before starting an assessment.")
    for tool in selected:
        if not incompatibility(tool, url) and not restriction(tool, options, bool(session.headers)) and not command(tool):
            raise ValueError(f"{tool} is not installed. Open Tools first.")
    scan = dict(id=uuid.uuid4().hex, target=url, created=storage.now(), finished=None,
                status="queued", stage="queued", progress=0, findings=[], tools=selected,
                allow_private=allow_private, errors=[], coverage={}, steps=[], profile=profile,
                profile_settings=settings, active_authorized=active_authorized, duration_unlimited=True,
                estimates=estimates.build(profile,url,["moth"]+selected,storage.recent(), options=options, authenticated=bool(session.headers)),
                tool_scope={tool: scope(tool, profile) for tool in ["moth"] + selected})
    scan.update(options=options, authentication=session.public(), recheck_of=recheck_of)
    scan["tool_versions"] = {tool["id"]: tool["version"] or "system installation"
                             for tool in installed if tool["id"] in selected}
    with LOCK:
        if ACTIVE:
            raise ValueError("A scan is already running. Stop it or wait for completion.")
        cancel = threading.Event()
        storage.save(scan)
        ACTIVE[scan["id"]] = cancel
    threading.Thread(target=worker, args=(scan, cancel, session), daemon=True).start()
    return scan["id"]


def stop(scan_id):
    with LOCK:
        event = ACTIVE.get(scan_id)
        if event:
            event.set()
    return bool(event)


def basic_profile(scan, cancel, session=None, progress=None):
    p = get_profile(scan.get("profile", "low"))
    options = scan.get('options') or validate_options()
    headers = session.headers if session else {}
    kwargs = {'headers': headers} if headers else {}
    if p['pages'] == 1 or scan.get('recheck_of'):
        found, coverage = basic(scan['target'], scan['allow_private'], **kwargs)
        coverage['checked_urls'] = [scan['target']]
        return found, coverage
    queue = deque([(scan['target'], 0)])
    visited, found, errors = set(), [], []
    coverage = {}
    completed = 0
    checked_urls = []
    while queue and len(visited) < p['pages']:
        if cancel.is_set():
            raise Cancelled()
        url, depth = queue.popleft()
        if url in visited or excluded(url, options):
            continue
        visited.add(url)
        links = []
        try:
            results, page_coverage = basic(url, scan['allow_private'], discover=links if depth < p['depth'] else None, **kwargs)
            found.extend(results)
            completed += 1
            checked_urls.append(url)
            if progress:
                progress(dict(phase='pages', pages_checked=completed, page_limit=p['pages'], percent=None))
            if url == scan['target']:
                coverage.update(page_coverage)
            queue.extend((link, depth+1) for link in links if link not in visited and len(queue) < 1000)
        except Exception as exc:
            if url == scan['target']:
                raise
            errors.append(dict(tool='moth', message=url + ': ' + str(exc)[:2000]))
        if queue and cancel.wait(1 / options['rate']):
            raise Cancelled()
    coverage.update(coverage='Same-origin GET crawl; each page checked once; no redirects.', checked_urls=checked_urls, pages_checked=completed, pages_attempted=len(visited), page_limit=p['pages'], limit_reached=any(url not in visited for url, depth in queue), page_errors=errors)
    return found, coverage


def worker(scan, cancel, session=None):
    session = session or Session()
    def save():
        storage.save(session.redact(scan))
    try:
        scan.update(status="running", stage="Resolving target")
        save()
        resolve(scan["target"], scan["allow_private"])
        scan['stage'] = 'preflight'
        save()
        scan['preflight'] = preflight.inspect(scan['target'], scan['tools'], scan.get('profile', 'low'), scan.get('options') or validate_options(), bool(session.headers), cancel)
        if cancel.is_set():
            raise Cancelled()
        blocked = [row for row in scan['preflight'] if row['status'] == 'error']
        if blocked:
            scan['errors'].extend(dict(tool=row['tool'], message=row['message']) for row in blocked)
            scan.update(status='failed', stage='failed')
            return
        if session.headers:
            if excluded(session.verify_url, scan['options']):
                raise ValueError('The session verification URL is excluded.')
            scan['authentication'] = session.verify(scan['target'], scan['allow_private'])
            save()
        stages = ["moth"] + scan["tools"]
        successful = 0
        for index, tool in enumerate(stages):
            if cancel.is_set():
                raise Cancelled()
            scan.update(stage=tool, progress=int(index / len(stages) * 100))
            save()
            step = {"tool": tool, "status": "running", "started": storage.now()}
            scan["steps"].append(step)
            save()
            started = time.monotonic()
            skipped = threading.Event()
            tool_cancel = ToolCancel(cancel, skipped)
            with LOCK:
                CURRENT[scan['id']] = (tool, skipped)
            def progress(details):
                details = session.redact(details)
                step['details'] = {**step.get('details', {}), **details}
                for warning in details.get('warnings', []):
                    if warning not in scan.setdefault('warnings', []):
                        scan['warnings'].append(warning)
                if 'spider' in details:
                    scan['spider'] = details['spider']
                save()
            try:
                reason = incompatibility(tool, scan["target"]) or restriction(tool, scan.get("options") or validate_options(), bool(session.headers))
                if reason:
                    step.update(status="skipped", reason=reason)
                    continue
                if session.headers and tool in ("moth", "retire", "katana", "zap"):
                    session.verify(scan["target"], scan["allow_private"])
                if tool == "moth":
                    found, coverage = basic_profile(scan, tool_cancel, session, progress)
                    scan["coverage"] = coverage
                    scan["errors"].extend(coverage.get("page_errors", []))
                else:
                    kwargs = {"profile": scan.get("profile", "low"), "progress": progress,
                              "options": scan.get("options"), "session": session}
                    found = run_tool(tool, scan["target"], RUNS / scan["id"] / tool, tool_cancel, scan["allow_private"], **kwargs)
                if tool_cancel.is_set():
                    raise Cancelled()
                if session.headers and tool in ("moth", "retire", "katana", "zap"):
                    session.verify(scan["target"], scan["allow_private"])
                found = session.redact(found)
                existing = {f["id"] for f in scan["findings"]}
                scan["findings"] += [item for item in found if item["id"] not in existing]
                step["status"] = "completed"
                successful += 1
            except Cancelled:
                if cancel.is_set():
                    step['status'] = 'cancelled'
                    raise
                step.update(status='skipped', reason='Skipped by the user; coverage is incomplete.')
            except Exception as exc:
                step["status"] = "failed"
                scan["errors"].append({"tool": tool, "message": str(exc)[:2500]})
            finally:
                with LOCK:
                    CURRENT.pop(scan['id'], None)
                step["finished"] = storage.now()
                step["elapsed_seconds"] = time.monotonic() - started
                step["completion_order"] = sum("completion_order" in previous for previous in scan["steps"] if previous is not step)
            save()
        if cancel.is_set():
            raise Cancelled()
        scan.update(status=("completed" if not scan["errors"] and not scan.get("warnings") and not any(s.get("reason", "").startswith("Skipped by the user") for s in scan["steps"]) else "partial" if successful else "failed"),
                    progress=100, stage="finished")
    except Cancelled:
        scan.update(status="cancelled", stage="cancelled")
    except Exception as exc:
        scan.update(status="failed", stage="failed")
        scan["errors"].append({"tool": "moth", "message": str(exc)[:2500]})
    finally:
        directory = RUNS / scan["id"]
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file():
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        scan["errors"].append({"tool": "moth", "message": "Could not remove a temporary tool artifact. Review the local run directory."})
        scan["finished"] = storage.now()
        try:
            history = [s for s in storage.recent() if s['id'] != scan['id'] and s['target'] == scan['target'] and s['status'] in ('completed', 'partial')]
            baseline = next((s for s in history if context(s) == context(scan)), history[0] if history else None)
            scan['comparison'] = compare(scan, baseline)
            scan['grouped_findings'] = grouped(scan['findings'])
            if scan.get('recheck_of'):
                original = storage.get(scan['recheck_of']['scan'])
                old = next((f for f in grouped(original['findings']) if f['id'] == scan['recheck_of']['finding']), None) if original else None
                from .results import identity
                present = old and any(identity(f) == identity(old) for f in scan['grouped_findings'])
                complete = old and scan['status'] == 'completed' and set(old['source_tools']).issubset({s['tool'] for s in scan['steps'] if s['status'] == 'completed'})
                scan['recheck_result'] = 'persistent' if present else 'absent' if complete else 'incomplete'

            scan['priority_ids'] = [f['id'] for f in priorities(scan)]
            save()
        finally:
            with LOCK:
                ACTIVE.pop(scan["id"], None)
                CURRENT.pop(scan["id"], None)
