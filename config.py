"""
config.py — Application-wide constants and path helpers.
"""
import os

APP_NAME = "ScreenTimeMonitor"
POLL_INTERVAL = 2           # seconds between active-window checks
SERVER_PORT   = 5055
SERVER_HOST   = "127.0.0.1"

# Root data directory shared by all user instances.
DB_BASE_PATH = os.path.join(r"C:\ProgramData", APP_NAME)

# auth.json holds the parent's hashed admin credentials.
AUTH_FILE = os.path.join(DB_BASE_PATH, "auth.json")

# Minimum acceptable password length for --setup.
MIN_PASSWORD_LENGTH = 6

# PBKDF2 parameters — increase iterations if CPU headroom allows.
PBKDF2_ITERATIONS = 260_000
PBKDF2_SALT_BYTES  = 32

# Path helpers ----------------------------------------------------------------

def get_user_dir(username: str) -> str:
    """Return (and create) the per-user data directory."""
    path = os.path.join(DB_BASE_PATH, username)
    os.makedirs(path, exist_ok=True)
    return path


def get_db_path(username: str) -> str:
    """Return the absolute path to a user's SQLite database file."""
    return os.path.join(get_user_dir(username), "data.db")


# Asset / template paths relative to this file's directory ------------------
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR    = os.path.join(BASE_DIR, "assets")
ICON_PATH     = os.path.join(ASSETS_DIR, "icon.png")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR    = os.path.join(BASE_DIR, "static")
