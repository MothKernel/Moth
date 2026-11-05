"""Short-lived SQLite connections; workers never share a connection."""
import json
import sqlite3
from datetime import datetime, timezone
from .config import DATA


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    db = sqlite3.connect(DATA / "moth.sqlite3", timeout=15)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, created TEXT, body TEXT)")
    return db


def save(scan):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO scans VALUES (?, ?, ?)",
                   (scan["id"], scan["created"], json.dumps(scan, ensure_ascii=False)))


def get(scan_id):
    with connect() as db:
        row = db.execute("SELECT body FROM scans WHERE id=?", (scan_id,)).fetchone()
    return json.loads(row[0]) if row else None


def recent():
    with connect() as db:
        rows = db.execute("SELECT body FROM scans ORDER BY created DESC LIMIT 50").fetchall()
    return [json.loads(row[0]) for row in rows]


def recover():
    for scan in recent():
        if scan["status"] in ("queued", "running", "stopping"):
            scan.update(status="interrupted", stage="Application stopped before completion", finished=now())
            save(scan)
