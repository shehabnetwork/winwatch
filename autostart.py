"""
autostart.py — Write / remove the HKCU auto-start registry key.

Registry path:
    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
Value name: ScreenTimeMonitor
Value data: "<absolute path to the .exe>"

Using HKCU means no admin elevation is required; the app auto-starts only
for the currently logged-in user, which is exactly what we want (each kid's
account gets its own instance).

Usage (from the command line or setup flow):
    python autostart.py --install   # register auto-start for this user
    python autostart.py --remove    # remove the auto-start entry

Both functions are also importable from main.py / setup code.
"""

import os
import sys

from config import APP_NAME

# winreg is only available on Windows.
try:
    import winreg  # type: ignore[import]
    _WINREG_AVAILABLE = True
except ImportError:
    _WINREG_AVAILABLE = False

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def install_autostart(exe_path: str | None = None) -> None:
    """
    Register the current executable under the HKCU Run key.

    *exe_path* defaults to sys.executable (the running Python interpreter /
    frozen .exe path).  Pass an explicit path when calling from a setup
    wrapper that knows the final .exe location.
    """
    if not _WINREG_AVAILABLE:
        raise RuntimeError("winreg is not available on this platform.")

    if exe_path is None:
        exe_path = sys.executable

    exe_path = os.path.abspath(exe_path)

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        _RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')


def remove_autostart() -> None:
    """Remove the HKCU Run key entry for this application (if it exists)."""
    if not _WINREG_AVAILABLE:
        raise RuntimeError("winreg is not available on this platform.")

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        pass  # Key did not exist — nothing to remove.


def is_autostart_installed() -> bool:
    """Return True if the HKCU Run entry exists for this application."""
    if not _WINREG_AVAILABLE:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("--install", "--remove"):
        print(f"Usage: {sys.argv[0]} --install | --remove")
        sys.exit(1)

    if sys.argv[1] == "--install":
        install_autostart()
        print(f"Auto-start registered for '{APP_NAME}'.")
    else:
        remove_autostart()
        print(f"Auto-start entry removed for '{APP_NAME}'.")
