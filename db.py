"""
db.py — SQLite schema initialisation and all CRUD operations.

All timestamps are stored as ISO 8601 strings (UTC).
Duration is stored in whole seconds; computed only when a session is closed.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from config import get_db_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect(username: str) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory for dict-like rows."""
    conn = sqlite3.connect(get_db_path(username))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent readers
    return conn


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration(start_iso: str, end_iso: str) -> int:
    """Return whole-second duration between two ISO 8601 strings."""
    fmt = "%Y-%m-%dT%H:%M:%S.%f%z"
    try:
        s = datetime.fromisoformat(start_iso)
        e = datetime.fromisoformat(end_iso)
        return max(0, int((e - s).total_seconds()))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_APP_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS app_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    NOT NULL,
    app_name         TEXT    NOT NULL,
    exe_path         TEXT,
    window_title     TEXT,
    start_time       TEXT    NOT NULL,
    end_time         TEXT,
    duration_seconds INTEGER
);
"""

_LOGIN_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS login_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    NOT NULL,
    login_time       TEXT    NOT NULL,
    logout_time      TEXT,
    duration_seconds INTEGER,
    source           TEXT
);
"""


def init_db(username: str) -> None:
    """Create the DB file and tables for *username* if they do not exist."""
    conn = _connect(username)
    with conn:
        conn.execute(_APP_SESSIONS_DDL)
        conn.execute(_LOGIN_SESSIONS_DDL)
    conn.close()


# ---------------------------------------------------------------------------
# App-session CRUD
# ---------------------------------------------------------------------------

def insert_app_session(
    username: str,
    app_name: str,
    exe_path: Optional[str],
    window_title: Optional[str],
    start_time: Optional[str] = None,
) -> int:
    """Open a new app session row; returns the row id."""
    start_time = start_time or _iso_now()
    conn = _connect(username)
    with conn:
        cur = conn.execute(
            """
            INSERT INTO app_sessions
                (username, app_name, exe_path, window_title, start_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, app_name, exe_path, window_title, start_time),
        )
        row_id = cur.lastrowid
    conn.close()
    return row_id


def close_app_session(
    username: str,
    row_id: int,
    end_time: Optional[str] = None,
) -> None:
    """Fill end_time and duration_seconds for the given row."""
    end_time = end_time or _iso_now()
    conn = _connect(username)
    with conn:
        row = conn.execute(
            "SELECT start_time FROM app_sessions WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            return
        duration = _duration(row["start_time"], end_time)
        conn.execute(
            "UPDATE app_sessions SET end_time = ?, duration_seconds = ? WHERE id = ?",
            (end_time, duration, row_id),
        )
    conn.close()


# ---------------------------------------------------------------------------
# Login-session CRUD
# ---------------------------------------------------------------------------

def insert_login_session(
    username: str,
    login_time: Optional[str] = None,
    source: str = "startup",
) -> int:
    """Open a new login session row; returns the row id."""
    login_time = login_time or _iso_now()
    conn = _connect(username)
    with conn:
        cur = conn.execute(
            """
            INSERT INTO login_sessions (username, login_time, source)
            VALUES (?, ?, ?)
            """,
            (username, login_time, source),
        )
        row_id = cur.lastrowid
    conn.close()
    return row_id


def close_login_session(
    username: str,
    row_id: int,
    logout_time: Optional[str] = None,
) -> None:
    """Fill logout_time and duration_seconds for the given row."""
    logout_time = logout_time or _iso_now()
    conn = _connect(username)
    with conn:
        row = conn.execute(
            "SELECT login_time FROM login_sessions WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            return
        duration = _duration(row["login_time"], logout_time)
        conn.execute(
            """
            UPDATE login_sessions
               SET logout_time = ?, duration_seconds = ?
             WHERE id = ?
            """,
            (logout_time, duration, row_id),
        )
    conn.close()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_app_sessions(
    username: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    app_name: Optional[str] = None,
    exe_path: Optional[str] = None,
    min_duration: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Return app sessions matching the supplied filters.

    When *username* is None, scan **all** per-user databases found in the
    ProgramData directory and merge the results.
    """
    usernames = _resolve_usernames(username)
    rows: list[dict[str, Any]] = []
    for uname in usernames:
        try:
            rows.extend(_query_app_sessions(uname, date_from, date_to, app_name, exe_path, min_duration))
        except Exception:
            pass
    return rows


def get_login_sessions(
    username: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_duration: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Return login sessions matching the supplied filters (all users if *username* is None)."""
    usernames = _resolve_usernames(username)
    rows: list[dict[str, Any]] = []
    for uname in usernames:
        try:
            rows.extend(_query_login_sessions(uname, date_from, date_to, min_duration))
        except Exception:
            pass
    return rows


def get_tracked_usernames() -> list[str]:
    """Return all usernames that have a database file in ProgramData."""
    import os
    from config import DB_BASE_PATH
    if not os.path.isdir(DB_BASE_PATH):
        return []
    users = []
    for entry in os.scandir(DB_BASE_PATH):
        if entry.is_dir() and os.path.isfile(os.path.join(entry.path, "data.db")):
            users.append(entry.name)
    return sorted(users)


# ---------------------------------------------------------------------------
# Private query implementations
# ---------------------------------------------------------------------------

def _resolve_usernames(username: Optional[str]) -> list[str]:
    if username:
        return [username]
    return get_tracked_usernames()


def _query_app_sessions(
    username: str,
    date_from: Optional[str],
    date_to: Optional[str],
    app_name: Optional[str],
    exe_path: Optional[str],
    min_duration: Optional[int],
) -> list[dict[str, Any]]:
    clauses = ["username = ?"]
    params: list[Any] = [username]

    if date_from:
        clauses.append("start_time >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("start_time <= ?")
        params.append(date_to + "T23:59:59")
    if app_name:
        clauses.append("app_name LIKE ?")
        params.append(f"%{app_name}%")
    if exe_path:
        clauses.append("exe_path LIKE ?")
        params.append(f"%{exe_path}%")
    if min_duration is not None:
        clauses.append("(duration_seconds IS NULL OR duration_seconds >= ?)")
        params.append(min_duration)

    sql = f"SELECT * FROM app_sessions WHERE {' AND '.join(clauses)} ORDER BY start_time DESC"
    conn = _connect(username)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def _query_login_sessions(
    username: str,
    date_from: Optional[str],
    date_to: Optional[str],
    min_duration: Optional[int],
) -> list[dict[str, Any]]:
    clauses = ["username = ?"]
    params: list[Any] = [username]

    if date_from:
        clauses.append("login_time >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("login_time <= ?")
        params.append(date_to + "T23:59:59")
    if min_duration is not None:
        clauses.append("(duration_seconds IS NULL OR duration_seconds >= ?)")
        params.append(min_duration)

    sql = f"SELECT * FROM login_sessions WHERE {' AND '.join(clauses)} ORDER BY login_time DESC"
    conn = _connect(username)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows
