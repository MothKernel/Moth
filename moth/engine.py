import json
import threading
import uuid
import time
from collections import deque
from .profiles import get_profile, incompatibility, scope
from . import estimates
from . import storage
from .adapters import Cancelled, run_tool
from .checks import basic
from .config import RUNS
from .targets import normalize, resolve
from .tools import command, metadata, catalog

LOCK = threading.Lock()
ACTIVE = {}


def start(target, selected, authorized, allow_private=False, profile="low", active_authorized=False):
    if not authorized:
        raise ValueError("Confirm that you have permission to assess this target.")
    settings = get_profile(profile)
    if profile in ("high", "ultra") and not active_authorized:
        raise ValueError("Confirm permission for active checks and additional server ports before using High or Ultra.")
    url = normalize(target)
    if profile == "ultra":
        from .tools import REGISTRY
        selected = [tool["id"] for tool in REGISTRY]
    # Network resolution belongs in the worker; the UI stays responsive.
    selected = list(dict.fromkeys(selected))
    if len(selected) > 10 or any(not metadata(tool) for tool in selected):
        raise ValueError("Unknown tool selection.")
    installed = catalog()
    if any(tool["id"] in selected and tool["status"] in ("queued", "installing") for tool in installed):
        raise ValueError("Wait for the selected tools to finish installing or updating before starting an assessment.")
    for tool in selected:
        if not incompatibility(tool, url) and not command(tool):
            raise ValueError(f"{tool} is not installed. Open Tools first.")
    scan = dict(id=uuid.uuid4().hex, target=url, created=storage.now(), finished=None,
                status="queued", stage="queued", progress=0, findings=[], tools=selected,
                allow_private=allow_private, errors=[], coverage={}, steps=[], profile=profile,
                profile_settings=settings, active_authorized=active_authorized, duration_unlimited=True,
                estimates=estimates.build(profile,url,["moth"]+selected,storage.recent()),
                tool_scope={tool: scope(tool, profile) for tool in ["moth"] + selected})
    scan["tool_versions"] = {tool["id"]: tool["version"] or "system installation"
                             for tool in installed if tool["id"] in selected}
    with LOCK:
        if ACTIVE:
            raise ValueError("A scan is already running. Stop it or wait for completion.")
        cancel = threading.Event()
        storage.save(scan)
        ACTIVE[scan["id"]] = cancel
    threading.Thread(target=worker, args=(scan, cancel), daemon=True).start()
    return scan["id"]


def stop(scan_id):
    with LOCK:
        event = ACTIVE.get(scan_id)
        if event:
            event.set()
    return bool(event)


def basic_profile(scan, cancel):
    p = get_profile(scan.get("profile", "low"))
    if p['pages'] == 1:
        return basic(scan['target'], scan['allow_private'])
    queue = deque([(scan['target'], 0)])
    visited, found, errors = set(), [], []
    coverage = {}
    completed = 0
    while queue and len(visited) < p['pages']:
        if cancel.is_set():
            raise Cancelled()
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        links = []
        try:
            results, page_coverage = basic(url, scan['allow_private'], discover=links if depth < p['depth'] else None)
            found.extend(results)
            completed += 1
            if url == scan['target']:
                coverage.update(page_coverage)
            queue.extend((link, depth+1) for link in links if link not in visited and len(queue) < 1000)
        except Exception as exc:
            if url == scan['target']:
                raise
            errors.append(dict(tool='moth', message=url + ': ' + str(exc)[:2000]))
        if queue and cancel.wait(1 / p['rate']):
            raise Cancelled()
    coverage.update(coverage='Same-origin GET crawl; each page checked once; no redirects.', pages_checked=completed, pages_attempted=len(visited), page_limit=p['pages'], limit_reached=any(url not in visited for url, depth in queue), page_errors=errors)
    return found, coverage


def worker(scan, cancel):
    try:
        scan.update(status="running", stage="Resolving target")
        storage.save(scan)
        resolve(scan["target"], scan["allow_private"])
        stages = ["moth"] + scan["tools"]
        successful = 0
        for index, tool in enumerate(stages):
            if cancel.is_set():
                raise Cancelled()
            scan.update(stage=tool, progress=int(index / len(stages) * 100))
            storage.save(scan)
            step = {"tool": tool, "status": "running", "started": storage.now()}
            scan["steps"].append(step)
            storage.save(scan)
            started = time.monotonic()
            try:
                reason = incompatibility(tool, scan["target"])
                if reason:
                    step.update(status="skipped", reason=reason)
                    continue
                if tool == "moth":
                    found, coverage = basic_profile(scan, cancel)
                    scan["coverage"] = coverage
                    scan["errors"].extend(coverage.get("page_errors", []))
                else:
                    kwargs = {"profile": scan.get("profile", "low")}
                    if tool == "zap":
                        def progress(details):
                            step["details"] = details
                            if "spider" in details:
                                scan["spider"] = details["spider"]
                            storage.save(scan)
                        kwargs["progress"] = progress
                    found = run_tool(tool, scan["target"], RUNS / scan["id"] / tool, cancel, scan["allow_private"], **kwargs)
                existing = {f["id"] for f in scan["findings"]}
                scan["findings"] += [item for item in found if item["id"] not in existing]
                step["status"] = "completed"
                successful += 1
            except Cancelled:
                step["status"] = "cancelled"
                raise
            except Exception as exc:
                step["status"] = "failed"
                scan["errors"].append({"tool": tool, "message": str(exc)[:2500]})
            finally:
                step["finished"] = storage.now()
                step["elapsed_seconds"] = time.monotonic() - started
                step["completion_order"] = sum("completion_order" in previous for previous in scan["steps"] if previous is not step)
            storage.save(scan)
        if cancel.is_set():
            raise Cancelled()
        scan.update(status=("completed" if not scan["errors"] else "partial" if successful else "failed"),
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
            storage.save(scan)
        finally:
            with LOCK:
                ACTIVE.pop(scan["id"], None)
