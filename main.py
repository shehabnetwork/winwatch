"""
main.py — Entry point for Screen Time Monitor.

Usage
-----
  main.py --setup      First-run setup: create auth.json, register auto-start.
  main.py              Normal operation: verify credentials, start monitor +
                       web server + system tray.

The script detects the current Windows username via os.getlogin() and uses
that as the key for database isolation.

Shutdown sequence (triggered by tray "Exit"):
  1. WindowMonitor.stop() — closes open app session, stops poll thread.
  2. Close the open login session row.
  3. Flask server is a daemon thread — it exits automatically.
  4. TrayApp.stop() — hides the tray icon.
"""

import os
import sys
import getpass
from tkinter import messagebox

import auth
import db
import server
from autostart import install_autostart, is_autostart_installed
from config import APP_NAME
from monitor import WindowMonitor
from tray import TrayApp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_username() -> str:
    """Return the Windows username of the running process."""
    try:
        return os.getlogin()
    except Exception:
        return getpass.getuser()


# ---------------------------------------------------------------------------
# --setup flow
# ---------------------------------------------------------------------------

def run_setup() -> None:
    """
    Interactive first-run setup:
      1. Prompt for admin username + password (min 6 chars).
      2. Hash and store credentials in auth.json.
      3. Register HKCU auto-start for the current executable.
    """
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()

    messagebox.showinfo(
        f"{APP_NAME} — First-Run Setup",
        "Welcome to Screen Time Monitor.\n\n"
        "You will now create an admin password that protects the Exit and\n"
        "Change Password menu options in the system tray.\n\n"
        "Please choose a username and a password of at least 6 characters.",
    )
    root.destroy()

    while True:
        creds = auth.prompt_credentials_dialog(
            title=f"{APP_NAME} — Create Admin Account",
            prompt="Create an admin username and password:",
        )
        if creds is None:
            _abort("Setup cancelled.  Run with --setup again to configure credentials.")
            return

        username, password = creds
        try:
            auth.setup_credentials(username, password)
            break
        except ValueError as exc:
            root2 = __import__("tkinter").Tk()
            root2.withdraw()
            messagebox.showwarning("Invalid Input", str(exc))
            root2.destroy()

    # Register auto-start for the current user if not already set.
    try:
        if not is_autostart_installed():
            install_autostart()
    except RuntimeError:
        pass  # Non-Windows environment; skip.

    root3 = __import__("tkinter").Tk()
    root3.withdraw()
    messagebox.showinfo(
        f"{APP_NAME} — Setup Complete",
        "Setup complete!\n\n"
        "Run the application normally (without --setup) to start monitoring.",
    )
    root3.destroy()


def _abort(message: str) -> None:
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(APP_NAME, message)
        r.destroy()
    except Exception:
        print(message, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Normal startup
# ---------------------------------------------------------------------------

def run_monitor() -> None:
    """Start the monitoring agent for the current user."""
    # Guard: credentials must be configured before we start.
    if not auth.credentials_configured():
        _abort(
            "No admin credentials found.\n\n"
            "Please run:\n    ScreenTimeMonitor.exe --setup\n\n"
            "to configure the admin password before starting."
        )

    username = _current_username()

    # Initialise database.
    db.init_db(username)

    # Record login session.
    login_row_id = db.insert_login_session(username, source="startup")

    # Start the active-window monitor in a background thread.
    monitor = WindowMonitor(username)
    monitor.start()

    # Start the Flask web server in a daemon thread.
    server.start_server()

    # --- Shutdown callback (called from TrayApp after password check) -------
    def on_exit() -> None:
        monitor.stop()
        db.close_login_session(username, login_row_id)
        # Flask thread is daemon=True; it will exit when the process does.

    # Wire Windows shutdown / ctrl+close so we close open sessions cleanly.
    _register_ctrl_handler(monitor, username, login_row_id)

    # Start the system tray (blocks until the icon is stopped).
    tray = TrayApp(username=username, on_exit=on_exit)
    tray.run()

    # Tray has exited; ensure sessions are closed even if on_exit wasn't called.
    monitor.stop()
    try:
        db.close_login_session(username, login_row_id)
    except Exception:
        pass


def _register_ctrl_handler(
    monitor: "WindowMonitor",
    username: str,
    login_row_id: int,
) -> None:
    """
    Register a Win32 console control handler so we close sessions cleanly on
    Windows shutdown / logoff / CTRL+C.  Silently skipped on non-Windows.
    """
    try:
        import win32api  # type: ignore[import]

        def _handler(event: int) -> bool:  # noqa: ANN001
            monitor.stop()
            try:
                db.close_login_session(username, login_row_id)
            except Exception:
                pass
            return False  # Let Windows continue with default handling.

        win32api.SetConsoleCtrlHandler(_handler, True)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--setup" in sys.argv:
        run_setup()
    else:
        run_monitor()
