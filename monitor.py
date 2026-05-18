"""
monitor.py — Active-window polling loop and login-session bookkeeping.

Runs in a background daemon thread.  The main thread (tray loop) owns the
start/stop lifecycle.

Windows APIs used:
  win32gui.GetForegroundWindow()          — HWND of the active window
  win32gui.GetWindowText(hwnd)            — visible title bar text
  win32process.GetWindowThreadProcessId() — (thread_id, pid) for the HWND
  psutil.Process(pid).exe()               — full path to the process EXE

Access-denied errors for system/protected processes are silently ignored;
the monitor will skip that poll cycle and try again next interval.
"""

import os
import threading
import time
from typing import Optional, Tuple

from config import POLL_INTERVAL
import db

# Win32 imports are Windows-only; guard so the module can be imported for
# testing on non-Windows platforms without crashing.
try:
    import win32gui
    import win32process
    import psutil
    _WINDOWS = True
except ImportError:
    _WINDOWS = False


# ---------------------------------------------------------------------------
# Window-inspection helpers
# ---------------------------------------------------------------------------

def get_active_window() -> Optional[Tuple[Optional[str], str, str]]:
    """
    Return (exe_path, app_name, window_title) for the foreground window.

    *exe_path* may be None if the process is inaccessible (system process).
    *app_name* is the lower-cased stem of the EXE filename (e.g. "chrome").
    Returns None if nothing meaningful is in the foreground.
    """
    if not _WINDOWS:
        return None

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None

        window_title: str = win32gui.GetWindowText(hwnd) or ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0:
            return None

        exe_path: Optional[str] = None
        app_name = "unknown"
        try:
            proc = psutil.Process(pid)
            exe_path = proc.exe()
            app_name = os.path.splitext(os.path.basename(exe_path))[0].lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
            # System / protected process — use the window title as fallback name.
            if window_title:
                app_name = window_title.split(" ")[0].lower()

        return exe_path, app_name, window_title
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class WindowMonitor:
    """
    Background thread that polls the active window every POLL_INTERVAL seconds
    and writes open/close records to the SQLite database.
    """

    def __init__(self, username: str) -> None:
        self._username = username
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="WindowMonitor")

        # Currently tracked session state.
        self._current_app_name: Optional[str] = None
        self._current_row_id: Optional[int] = None

    # ------------------------------------------------------------------
    # Public control interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the polling thread."""
        self._thread.start()

    def stop(self) -> None:
        """Signal the thread to stop and wait for it to finish cleanly."""
        self._stop_event.set()
        self._thread.join(timeout=POLL_INTERVAL * 3)
        self._close_current_session()

    # ------------------------------------------------------------------
    # Internal poll loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception:
                pass  # Never crash the monitor thread.
            self._stop_event.wait(POLL_INTERVAL)

        # Thread is stopping — close any open session.
        self._close_current_session()

    def _poll(self) -> None:
        result = get_active_window()
        if result is None:
            return

        exe_path, app_name, window_title = result

        # Ignore truly blank or idle states.
        if not app_name or app_name in ("", "unknown") and not window_title:
            return

        if app_name != self._current_app_name:
            # App has changed: close the previous session and open a new one.
            self._close_current_session()
            self._current_app_name = app_name
            self._current_row_id = db.insert_app_session(
                self._username,
                app_name,
                exe_path,
                window_title,
            )
        else:
            # Same app: update the window title in-place (best-effort, no re-insert).
            # This keeps the record's title reasonably fresh without extra writes.
            if self._current_row_id is not None and window_title:
                try:
                    _update_window_title(self._username, self._current_row_id, window_title)
                except Exception:
                    pass

    def _close_current_session(self) -> None:
        if self._current_row_id is not None:
            try:
                db.close_app_session(self._username, self._current_row_id)
            except Exception:
                pass
            finally:
                self._current_row_id = None
                self._current_app_name = None


# ---------------------------------------------------------------------------
# Helper: update window title without changing the rest of the row
# ---------------------------------------------------------------------------

def _update_window_title(username: str, row_id: int, title: str) -> None:
    import sqlite3
    from config import get_db_path
    conn = sqlite3.connect(get_db_path(username))
    with conn:
        conn.execute(
            "UPDATE app_sessions SET window_title = ? WHERE id = ?",
            (title, row_id),
        )
    conn.close()
