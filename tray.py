"""
tray.py — System tray icon and context menu.

Menu items:
  • Open Dashboard      → opens http://localhost:5055 in the default browser
  • View Data Folder    → opens File Explorer at the ProgramData directory
  • ──────────────────
  • Change Password     → password-protected; prompts current → new + confirm
  • Exit                → password-protected; graceful shutdown
"""

import subprocess
import threading
import webbrowser
from tkinter import messagebox
from typing import Callable, Optional

from PIL import Image
import pystray

import auth
from config import APP_NAME, DB_BASE_PATH, SERVER_HOST, SERVER_PORT, ICON_PATH


def _load_icon() -> Image.Image:
    """Load the tray icon; fall back to a plain coloured square if missing."""
    try:
        return Image.open(ICON_PATH).convert("RGBA")
    except Exception:
        img = Image.new("RGBA", (32, 32), color=(37, 99, 235, 255))
        return img


def _open_data_folder() -> None:
    try:
        subprocess.Popen(["explorer", DB_BASE_PATH])
    except Exception:
        pass


def _password_gate(action_name: str) -> Optional[tuple[str, str]]:
    """
    Show the credential dialog and return (username, password) on success,
    or None if cancelled / wrong credentials.

    Shows an error messagebox if credentials are incorrect.
    """
    creds = auth.prompt_credentials_dialog(
        title=f"Screen Time Monitor — {action_name}",
        prompt=f"Enter admin password to {action_name.lower()}:",
    )
    if creds is None:
        return None  # User cancelled.
    username, password = creds
    if not auth.verify_credentials(username, password):
        messagebox.showerror(
            "Authentication Failed",
            "Incorrect username or password.\nThe service will keep running.",
        )
        return None
    return creds


# ---------------------------------------------------------------------------
# TrayApp
# ---------------------------------------------------------------------------

class TrayApp:
    """
    Wraps a pystray.Icon instance with the Screen Time Monitor menu.

    *on_exit* is called (in a separate thread) after authentication succeeds
    and the user confirms exit.  The caller (main.py) is responsible for
    stopping the monitor and Flask server.
    """

    def __init__(self, username: str, on_exit: Callable[[], None]) -> None:
        self._username = username
        self._on_exit_callback = on_exit
        self._icon: Optional[pystray.Icon] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build the icon and start the pystray event loop (blocks)."""
        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", self._open_dashboard),
            pystray.MenuItem("View Data Folder", lambda icon, item: _open_data_folder()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Change Password", self._change_password),
            pystray.MenuItem("Exit", self._exit),
        )
        self._icon = pystray.Icon(
            APP_NAME,
            _load_icon(),
            f"{APP_NAME} — Protected",
            menu,
        )
        self._icon.run()

    def stop(self) -> None:
        """Stop the tray icon from outside (e.g. during a clean shutdown)."""
        if self._icon is not None:
            self._icon.stop()

    # ------------------------------------------------------------------
    # Menu handlers (run on pystray's internal thread)
    # ------------------------------------------------------------------

    def _open_dashboard(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:  # noqa: ARG002
        url = f"http://{SERVER_HOST}:{SERVER_PORT}/"
        webbrowser.open(url)

    def _exit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:  # noqa: ARG002
        creds = _password_gate("Exit")
        if creds is None:
            return
        # Run shutdown in a separate thread so we don't deadlock pystray.
        threading.Thread(target=self._do_exit, daemon=True).start()

    def _do_exit(self) -> None:
        if self._icon is not None:
            self._icon.stop()
        self._on_exit_callback()

    def _change_password(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:  # noqa: ARG002
        # Step 1: verify current password.
        creds = _password_gate("Change Password")
        if creds is None:
            return

        current_username, _ = creds

        # Step 2: collect new password.
        new_password = auth.prompt_new_password_dialog()
        if new_password is None:
            return  # User cancelled.

        try:
            auth.setup_credentials(current_username, new_password)
            messagebox.showinfo(
                "Password Changed",
                "Your password has been updated successfully.",
            )
        except ValueError as exc:
            messagebox.showerror("Error", str(exc))
        except OSError as exc:
            messagebox.showerror("Error", f"Could not save credentials:\n{exc}")
