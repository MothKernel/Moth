import json
import threading
import uuid
from . import storage
from .adapters import Cancelled, run_tool
from .checks import basic
from .config import RUNS
from .targets import normalize, resolve
from .tools import command, metadata, catalog

LOCK = threading.Lock()
ACTIVE = {}


def start(target, selected, authorized, allow_private=False):
    if not authorized:
        raise ValueError("Confirm that you have permission to assess this target.")
    url = normalize(target)
    # Network resolution belongs in the worker; the UI stays responsive.
    selected = list(dict.fromkeys(selected))
    if len(selected) > 10 or any(not metadata(tool) for tool in selected):
        raise ValueError("Unknown tool selection.")
    installed = catalog()
    if any(tool["id"] in selected and tool["status"] in ("queued", "installing") for tool in installed):
        raise ValueError("Wait for the selected tools to finish installing or updating before starting an assessment.")
    for tool in selected:
        if not command(tool):
            raise ValueError(f"{tool} is not installed. Open Tools first.")
    scan = dict(id=uuid.uuid4().hex, target=url, created=storage.now(), finished=None,
                status="queued", stage="queued", progress=0, findings=[], tools=selected,
                allow_private=allow_private, errors=[], coverage={}, steps=[])
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
            step = {"tool": tool, "status": "running"}
            scan["steps"].append(step)
            try:
                if tool == "moth":
                    found, coverage = basic(scan["target"], scan["allow_private"])
                    scan["coverage"] = coverage
                else:
                    found = run_tool(tool, scan["target"], RUNS / scan["id"] / tool, cancel, scan["allow_private"])
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
