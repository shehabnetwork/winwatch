"""
server.py — Flask HTTP server (localhost:5055 only).

Endpoints
---------
GET  /                          Render the dashboard HTML page
GET  /api/app-sessions          JSON; accepts filter query params
GET  /api/login-sessions        JSON; accepts filter query params
GET  /api/users                 JSON list of tracked usernames
GET  /export/app-sessions.csv   Streamed CSV download
GET  /export/login-sessions.csv Streamed CSV download

All endpoints are bound to 127.0.0.1 and are not reachable from other machines.

Filter query parameters (all optional, applied server-side):
  username     — exact match
  app_name     — partial match (LIKE)
  exe_path     — partial match (LIKE)
  date_from    — ISO 8601 date string (inclusive lower bound)
  date_to      — ISO 8601 date string (inclusive upper bound)
  min_duration — minimum duration_seconds (integer)
"""

import csv
import io
import threading
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import db
from config import SERVER_HOST, SERVER_PORT, TEMPLATES_DIR, STATIC_DIR

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR,
)
app.config["PROPAGATE_EXCEPTIONS"] = True


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _app_session_filters() -> dict[str, Any]:
    args = request.args
    return {
        "username":     args.get("username") or None,
        "date_from":    args.get("date_from") or None,
        "date_to":      args.get("date_to") or None,
        "app_name":     args.get("app_name") or None,
        "exe_path":     args.get("exe_path") or None,
        "min_duration": _int_or_none(args.get("min_duration")),
    }


def _login_session_filters() -> dict[str, Any]:
    args = request.args
    return {
        "username":     args.get("username") or None,
        "date_from":    args.get("date_from") or None,
        "date_to":      args.get("date_to") or None,
        "min_duration": _int_or_none(args.get("min_duration")),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard() -> str:
    return render_template("dashboard.html")


@app.route("/api/users")
def api_users() -> Response:
    users = db.get_tracked_usernames()
    return jsonify(users)


@app.route("/api/app-sessions")
def api_app_sessions() -> Response:
    rows = db.get_app_sessions(**_app_session_filters())
    return jsonify(rows)


@app.route("/api/login-sessions")
def api_login_sessions() -> Response:
    rows = db.get_login_sessions(**_login_session_filters())
    return jsonify(rows)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

_APP_SESSION_FIELDS = [
    "id", "username", "app_name", "exe_path",
    "window_title", "start_time", "end_time", "duration_seconds",
]

_LOGIN_SESSION_FIELDS = [
    "id", "username", "login_time", "logout_time", "duration_seconds", "source",
]


def _stream_csv(rows: list[dict[str, Any]], fieldnames: list[str]):
    """Generator that yields CSV rows as UTF-8 strings."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    yield buf.getvalue()
    for row in rows:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n")
        writer.writerow(row)
        yield buf.getvalue()


@app.route("/export/app-sessions.csv")
def export_app_sessions() -> Response:
    rows = db.get_app_sessions(**_app_session_filters())
    return Response(
        stream_with_context(_stream_csv(rows, _APP_SESSION_FIELDS)),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=app-sessions.csv"},
    )


@app.route("/export/login-sessions.csv")
def export_login_sessions() -> Response:
    rows = db.get_login_sessions(**_login_session_filters())
    return Response(
        stream_with_context(_stream_csv(rows, _LOGIN_SESSION_FIELDS)),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=login-sessions.csv"},
    )


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

_server_thread: threading.Thread | None = None


def start_server() -> None:
    """Start the Flask server in a daemon background thread."""
    global _server_thread  # noqa: PLW0603

    def _run() -> None:
        # Use Werkzeug's built-in server; disable the reloader (not safe in threads).
        app.run(
            host=SERVER_HOST,
            port=SERVER_PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    _server_thread = threading.Thread(target=_run, daemon=True, name="FlaskServer")
    _server_thread.start()
