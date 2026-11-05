import json
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import engine, storage, tools
from .config import ROOT
from .reports import render

TOKEN = secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(app):
    storage.recover()
    yield
    with engine.LOCK:
        for cancel in engine.ACTIVE.values():
            cancel.set()


app = FastAPI(title="Moth", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def local_access(request: Request, call_next):
    host = request.url.hostname
    if host not in ("localhost", "127.0.0.1", "::1"):
        return JSONResponse({"detail": "Local access only."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        return JSONResponse({"detail": "Cross-origin access denied."}, status_code=403)
    if request.url.path.startswith("/api/"):
        if not secrets.compare_digest(request.headers.get("x-moth-token", ""), TOKEN):
            return JSONResponse({"detail": "Reload Moth to refresh your local session."}, status_code=403)
        size = request.headers.get("content-length", "0")
        if not size.isdigit() or int(size) > 16_384:
            return JSONResponse({"detail": "Request is too large."}, status_code=413)
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "static/index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)


class ScanRequest(BaseModel):
    target: str = Field(min_length=1, max_length=2048)
    tools: list[str] = Field(default_factory=list, max_length=10)
    authorized: bool = False
    allow_private: bool = False


@app.get("/api/tools")
def tool_list():
    return tools.catalog()


@app.post("/api/tools/{tool}/install", status_code=202)
def install(tool: str):
    try:
        tools.start_install(tool)
        return {"status": "installing"}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/scans")
def scan_list():
    return [{k: v for k, v in row.items() if k not in ("findings",)} | {"finding_count": len(row["findings"])} for row in storage.recent()]


@app.post("/api/scans", status_code=202)
def create_scan(body: ScanRequest):
    try:
        return {"id": engine.start(body.target, body.tools, body.authorized, body.allow_private)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def lookup(scan_id):
    result = storage.get(scan_id)
    if not result:
        raise HTTPException(404, "Scan not found.")
    return result


@app.get("/api/scans/{scan_id}")
def scan_detail(scan_id: str):
    return lookup(scan_id)


@app.post("/api/scans/{scan_id}/stop")
def stop_scan(scan_id: str):
    lookup(scan_id)
    return {"stopping": engine.stop(scan_id)}


@app.get("/api/scans/{scan_id}/report")
def report(scan_id: str, language: str = "en", format: str = "html"):
    scan = lookup(scan_id)
    if format == "json":
        return Response(json.dumps(scan, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="moth-{scan["id"]}.json"'})
    if format != "html":
        raise HTTPException(400, "Choose html or json.")
    return HTMLResponse(render(scan, language), headers={"Content-Disposition": f'attachment; filename="moth-{scan["id"]}.html"'})
