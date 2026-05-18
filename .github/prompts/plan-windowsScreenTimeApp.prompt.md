# Plan: Windows Screen Time Monitoring App

## Overview
Python-based Windows app that silently monitors active application usage and login sessions per user, runs as a system tray icon, and exposes a local web dashboard at `http://localhost:5055`. The dashboard supports live filtering by any field and CSV export. Each kid's Windows account gets its own auto-starting agent instance.

---

## Technology Stack
- **Python** (recommended for rapid dev + strong Windows API support)
- `pywin32` — Windows API (GetForegroundWindow, GetWindowText, win32evtlog)
- `psutil` — simpler EXE path lookup per process
- `pystray` + `Pillow` — system tray icon
- `sqlite3` (built-in) — data storage
- `Flask` — local HTTP server + Jinja2 templating (built-in)
- `hashlib` + `secrets` (built-in) — PBKDF2-HMAC-SHA256 password hashing; no third-party crypto dependency
- `pyinstaller` — package to .exe for distribution
- `winreg` (built-in) — auto-start registry

---

## Project Structure
```
Windows Screen Time App/
├── main.py              # Entry point: wires tray + monitor + web server
├── monitor.py           # Active window polling loop + session tracker
├── db.py                # SQLite schema + CRUD operations
├── server.py            # Flask HTTP server (localhost:5055)
├── tray.py              # System tray icon + menu
├── auth.py              # Credential setup, hashing, and verification
├── autostart.py         # Registry write/remove for HKCU Run key
├── config.py            # Constants (poll interval, DB path, port, etc.)
├── assets/
│   └── icon.png         # Tray icon (16x16 or 32x32)
├── templates/
│   └── dashboard.html   # Flask/Jinja2 dashboard template
├── static/
│   ├── style.css        # Dashboard styles
│   └── dashboard.js     # Filter + export logic (vanilla JS)
├── requirements.txt
└── build.spec           # PyInstaller spec file
```

---

## Database Schema (SQLite)

### `app_sessions`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | auto-increment |
| username | TEXT NOT NULL | Windows username |
| app_name | TEXT NOT NULL | exe stem (e.g., "chrome") |
| exe_path | TEXT | full path |
| window_title | TEXT | last observed title |
| start_time | TEXT NOT NULL | ISO 8601 |
| end_time | TEXT | NULL until closed |
| duration_seconds | INTEGER | computed on close |

### `login_sessions`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | auto-increment |
| username | TEXT NOT NULL | Windows username |
| login_time | TEXT NOT NULL | ISO 8601 |
| logout_time | TEXT | NULL if active |
| duration_seconds | INTEGER | computed on close |
| source | TEXT | "startup" or "eventlog" |

DB path: `C:\ProgramData\ScreenTimeMonitor\{username}\data.db`

---

## Implementation Phases

### Phase 1: Project Setup
- Create project folder structure
- `requirements.txt`: pywin32, psutil, pystray, Pillow, Flask, pyinstaller
- `config.py`: POLL_INTERVAL=2, DB_BASE_PATH, APP_NAME, SERVER_PORT=5055, SERVER_HOST="127.0.0.1", AUTH_FILE path
- First-run credential setup: if `auth.json` does not exist, `main.py --setup` prompts the parent (via a tkinter dialog) to set an admin username + password before the service starts; setup refuses to proceed with an empty or too-short password (min 6 chars)

### Phase 2: Database Layer (`db.py`)
- `init_db(username)` — creates DB file + tables if not exists
- `insert_app_session(username, app_name, exe_path, window_title, start_time)` → returns row id
- `close_app_session(row_id, end_time)` — fills end_time + duration_seconds
- `insert_login_session(username, login_time, source)` → returns row id
- `close_login_session(row_id, logout_time)` — fills logout_time + duration_seconds
- `get_app_sessions(username, date_from, date_to)` → list of rows
- `get_login_sessions(username, date_from, date_to)` → list of rows

### Phase 3: Monitor Loop (`monitor.py`)
- `get_active_window()` → (exe_path, app_name, window_title) using win32gui + psutil
- Polls every POLL_INTERVAL seconds in a background thread
- Tracks "current session": if app changes → close old session, open new one
- Graceful shutdown: close open session on stop signal
- Handles access-denied processes (system apps) by catching exceptions

### Phase 4: Login Tracking
- On app startup: `insert_login_session(username, now, "startup")` → store row_id
- On app exit (tray "Exit" or Windows shutdown via `win32api.SetConsoleCtrlHandler`): call `close_login_session(row_id, now)`
- Supplement: read System event log (IDs 7001/7002, no admin needed) for historical login data on first run

### Phase 5: Auth Module (`auth.py`)
- `setup_credentials(username, password)` — hashes password with PBKDF2-HMAC-SHA256 (random 32-byte salt, 260,000 iterations), stores `{username, salt, hash}` in `C:\ProgramData\ScreenTimeMonitor\auth.json`
- `verify_credentials(username, password)` → `True/False` — re-derives hash and compares with `hmac.compare_digest` (constant-time, prevents timing attacks)
- `credentials_configured()` → `bool` — checks if `auth.json` exists and is valid
- `prompt_credentials_dialog()` — tkinter modal dialog: username field + masked password field + OK/Cancel; returns `(username, password)` or `None` on cancel

### Phase 6: System Tray (`tray.py`)
- Menu items: **"Open Dashboard"** → opens `http://localhost:5055` in the default browser, "View Data Folder" → opens Explorer at ProgramData path, **"Exit"** (password-protected), **"Change Password"** (password-protected)
- **"Exit" flow**: clicking Exit calls `prompt_credentials_dialog()`; if `verify_credentials()` returns `False` or dialog is cancelled → show error messagebox and do nothing; if correct → close open DB session, stop monitor thread, stop Flask thread, destroy tray icon
- **"Change Password" flow**: prompts for current password first; if verified, prompts for new password (with confirmation field); calls `setup_credentials()` with new values
- Tray icon title (tooltip) shows "Screen Time Monitor — Protected"
- On startup: check `credentials_configured()`; if not → abort with a message directing parent to run `--setup` first

### Phase 7: Flask Web Server + Dashboard (`server.py` + `templates/dashboard.html`)

#### HTTP Endpoints
| Method | Route | Description |
|---|---|---|
| GET | `/` | Renders the dashboard HTML page |
| GET | `/api/app-sessions` | Returns JSON; accepts query params for filtering |
| GET | `/api/login-sessions` | Returns JSON; accepts query params for filtering |
| GET | `/api/users` | Returns list of tracked usernames |
| GET | `/export/app-sessions.csv` | Streams filtered results as a CSV download |
| GET | `/export/login-sessions.csv` | Streams filtered login sessions as a CSV download |

#### Filter Query Parameters (all optional, applied server-side)
- `username` — exact match
- `app_name` — partial match (LIKE)
- `exe_path` — partial match (LIKE)
- `date_from` / `date_to` — ISO 8601 date range
- `min_duration` — minimum session duration in seconds

#### Dashboard UI (`templates/dashboard.html` + `static/`)
- Single-page layout with two tabs: **App Sessions** and **Login Sessions**
- Filter bar per tab: username dropdown, app name text field, date-from/date-to pickers, min-duration field, **Apply** + **Reset** buttons
- Results table with sortable columns (vanilla JS)
- Summary row: total sessions, total duration for current filter
- Chart.js horizontal bar chart: top 10 apps by total time (updates on filter)
- **Export CSV** button → calls the matching `/export/` endpoint with current filter params
- Server runs on `127.0.0.1:5055` only — not accessible from other machines on the network
- Flask server starts in a `daemon=True` background thread; main thread owns the tray loop

### Phase 8: Auto-Start (`autostart.py`)
- `install_autostart(exe_path)` — writes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` using `winreg`
- `remove_autostart()` — removes the key
- Called once during first-time setup (a separate `setup.exe` or just running `main.py --setup`)

### Phase 9: Packaging
- `build.spec` for PyInstaller: single-file `.exe`, hidden console, includes `assets/` and `templates/`
- Build command: `pyinstaller build.spec`
- Output: `dist/ScreenTimeMonitor.exe`

---

## Verification Steps
1. Run `main.py --setup` — confirm credential dialog appears; set a test password
2. Run `main.py` on Windows — confirm tray icon appears with "Protected" tooltip
3. Switch between apps — confirm `app_sessions` DB rows created with correct names and times
4. Exit and reopen — confirm previous session's `end_time` was written
5. Open `http://localhost:5055` — confirm dashboard loads with app + login session tabs
6. Apply filters (username, date range, app name) — confirm table updates correctly
7. Click "Export CSV" — confirm file downloads with the filtered rows
8. Click **Exit** from tray with wrong credentials — confirm service stays running and shows error
9. Click **Exit** with correct credentials — confirm service stops cleanly
10. Click **Change Password**, verify old password check works, then set new password
11. Run `autostart.py --install` — confirm app starts after login on next reboot
12. Test with a second Windows user account — confirm separate DB file created in ProgramData, and both users visible in the dashboard username dropdown

---

## Decisions / Scope
- **Language**: Python (faster iteration, all needed libraries available)
- **Visibility**: System tray icon only (no taskbar window)
- **Report format**: Live web dashboard at `http://localhost:5055` with server-side filtering and CSV export; no static file saved to disk
- **Multi-user**: Per-user instances via HKCU auto-start; data in shared ProgramData folder so parent can access
- **Login detection**: Primary = app startup timestamp; secondary = System event log (7001/7002)
- **Exit protection**: Password-protected tray exit using PBKDF2-HMAC-SHA256 hashing; credentials stored in `C:\ProgramData\ScreenTimeMonitor\auth.json` (never plain-text)
- **Excluded**: Real-time alerts, time limits/blocking, remote dashboard, mobile companion app

---

## Security Considerations

### Task Manager bypass
A determined kid could kill the process via Task Manager. The password-protected tray exit addresses casual attempts. To fully harden against Task Manager:
- **Option A (recommended later)**: Convert the monitor agent into a **Windows Service** (`pywin32` `win32serviceutil`) running under the SYSTEM account — services cannot be killed by a standard user account without admin rights
- **Option B**: Use Windows parental controls / Family Safety to block access to Task Manager on the kid's account (no code change needed)
- **Phase 9 scope**: Only Option A is in scope for future work; the current build uses the tray approach

### `auth.json` tampering
- File is stored in `C:\ProgramData\ScreenTimeMonitor\` which requires admin privileges to modify on a standard user account — kids cannot delete or overwrite it without elevation
- If the file is missing or corrupt at startup, the service refuses to start and shows a message directing the parent to re-run `--setup`
