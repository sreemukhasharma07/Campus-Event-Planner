"""Tiny SQLite store for event briefs."""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from .config import settings

_lock = threading.Lock()
_db = sqlite3.connect(settings.db_path, check_same_thread=False)
_db.row_factory = sqlite3.Row
_db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)")
_db.commit()


def _row(r) -> dict:
    return {**json.loads(r["data"]), "id": r["id"], "status": r["status"], "created_at": r["created_at"]}


def create(data: dict) -> dict:
    eid, now = uuid.uuid4().hex, datetime.now(timezone.utc).isoformat()
    with _lock:
        _db.execute("INSERT INTO events VALUES (?,?,?,?)", (eid, json.dumps(data), "draft", now))
        _db.commit()
    return {**data, "id": eid, "status": "draft", "created_at": now}


def list_all() -> list[dict]:
    with _lock:
        return [_row(r) for r in _db.execute("SELECT * FROM events ORDER BY created_at DESC")]


def get(eid: str) -> dict | None:
    with _lock:
        r = _db.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    return _row(r) if r else None


def delete(eid: str) -> bool:
    with _lock:
        n = _db.execute("DELETE FROM events WHERE id=?", (eid,)).rowcount
        _db.commit()
    return n > 0
