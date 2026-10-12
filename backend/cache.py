"""
cache.py — tiny SQLite key/value cache under /config/cache, so repeat lookups
don't hammer Scryfall / EDHREC and survive container restarts.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from backend.config import CACHE_DIR

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(Path(CACHE_DIR) / "cache.db"), check_same_thread=False)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, fetched_at REAL)"
        )
    return _conn


def get(key: str, max_age_hours: float) -> Any:
    with _lock:
        row = _db().execute("SELECT value, fetched_at FROM kv WHERE key = ?", (key,)).fetchone()
    if row is None or time.time() - row[1] > max_age_hours * 3600:
        return None
    return json.loads(row[0])


def put(key: str, value: Any) -> None:
    with _lock:
        _db().execute(
            "INSERT OR REPLACE INTO kv (key, value, fetched_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time()),
        )
        _db().commit()


def clear() -> None:
    with _lock:
        _db().execute("DELETE FROM kv")
        _db().commit()
