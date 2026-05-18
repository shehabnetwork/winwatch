# build.spec — PyInstaller configuration for ScreenTimeMonitor.exe
#
# Build command (from the project root):
#   pyinstaller build.spec
#
# Output: dist/ScreenTimeMonitor.exe  (single-file, no console window)
#
# Notes
# -----
# • windowed=True  hides the console (system-tray-only app).
# • upx=False      skips UPX compression; set True if UPX is on PATH.
# • The spec file uses relative paths so it works on any machine.

import os
import sys
from PyInstaller.building.api import PYZ, EXE, COLLECT
from PyInstaller.building.build_main import Analysis

block_cipher = None

HERE = os.path.dirname(os.path.abspath(SPEC))  # noqa: F821  (SPEC is injected by PyInstaller)

a = Analysis(
    [os.path.join(HERE, "main.py")],
    pathex=[HERE],
    binaries=[],
    datas=[
        # Include the templates directory.
        (os.path.join(HERE, "templates"), "templates"),
        # Include the static directory.
        (os.path.join(HERE, "static"),    "static"),
        # Include the tray icon.
        (os.path.join(HERE, "assets"),    "assets"),
    ],
    hiddenimports=[
        # pywin32 sub-modules are not always auto-detected.
        "win32api",
        "win32con",
        "win32gui",
        "win32process",
        "win32evtlog",
        "win32security",
        "winerror",
        "pywintypes",
        # Flask / Werkzeug internal modules.
        "flask",
        "werkzeug",
        "jinja2",
        # pystray backends.
        "pystray._win32",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ScreenTimeMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window — tray-only app.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(HERE, "assets", "icon.png"),
)
