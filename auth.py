"""
auth.py — Credential setup, hashing, and verification.

Credentials are stored in C:\\ProgramData\\ScreenTimeMonitor\\auth.json as:
    {
        "username": "<admin_username>",
        "salt":     "<hex-encoded 32-byte salt>",
        "hash":     "<hex-encoded PBKDF2-HMAC-SHA256 digest>"
    }

Password hashing: PBKDF2-HMAC-SHA256, 260,000 iterations, 32-byte random salt.
Comparison:        hmac.compare_digest — constant-time, prevents timing attacks.
Storage location:  C:\\ProgramData\\ScreenTimeMonitor\\ — requires admin rights to
                   modify on a standard user account.
"""
import hashlib
import hmac
import json
import os
import secrets
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Tuple

from config import AUTH_FILE, DB_BASE_PATH, MIN_PASSWORD_LENGTH, PBKDF2_ITERATIONS, PBKDF2_SALT_BYTES


# ---------------------------------------------------------------------------
# Core crypto helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt_bytes: Optional[bytes] = None) -> Tuple[str, str]:
    """
    Return (salt_hex, hash_hex) for *password*.

    If *salt_bytes* is not provided a fresh random salt is generated.
    """
    if salt_bytes is None:
        salt_bytes = secrets.token_bytes(PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        PBKDF2_ITERATIONS,
    )
    return salt_bytes.hex(), dk.hex()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_credentials(username: str, password: str) -> None:
    """
    Hash *password* and persist credentials to AUTH_FILE.

    Raises ValueError if the password is shorter than MIN_PASSWORD_LENGTH.
    Raises ValueError if username is empty.
    """
    username = username.strip()
    if not username:
        raise ValueError("Username must not be empty.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")

    salt_hex, hash_hex = _hash_password(password)
    payload = {"username": username, "salt": salt_hex, "hash": hash_hex}

    os.makedirs(DB_BASE_PATH, exist_ok=True)
    # Write atomically: temp file → rename.
    tmp_path = AUTH_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp_path, AUTH_FILE)


def verify_credentials(username: str, password: str) -> bool:
    """
    Return True iff *username* + *password* match the stored credentials.

    Returns False (never raises) on any error so the caller can treat it as
    an auth failure without exposing internal details.
    """
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        stored_username: str = data["username"]
        salt_bytes = bytes.fromhex(data["salt"])
        stored_hash = bytes.fromhex(data["hash"])
    except Exception:
        return False

    # Constant-time username comparison (pad to equal length).
    username_match = hmac.compare_digest(
        username.strip().encode("utf-8"),
        stored_username.encode("utf-8"),
    )

    _, candidate_hash_hex = _hash_password(password, salt_bytes)
    hash_match = hmac.compare_digest(
        bytes.fromhex(candidate_hash_hex),
        stored_hash,
    )

    return username_match and hash_match


def credentials_configured() -> bool:
    """Return True iff AUTH_FILE exists and contains the expected keys."""
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return all(k in data for k in ("username", "salt", "hash"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tkinter credential dialog
# ---------------------------------------------------------------------------

def prompt_credentials_dialog(
    title: str = "Screen Time Monitor — Authentication",
    prompt: str = "Enter admin credentials to continue:",
) -> Optional[Tuple[str, str]]:
    """
    Show a modal tkinter dialog asking for username + password.

    Returns (username, password) on OK, or None if cancelled / window closed.
    """
    result: list[Optional[Tuple[str, str]]] = [None]

    root = tk.Tk()
    root.withdraw()

    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.grab_set()

    # Centre on screen.
    dlg.update_idletasks()
    w, h = 340, 180
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    tk.Label(dlg, text=prompt, wraplength=300, justify="left").grid(
        row=0, column=0, columnspan=2, padx=16, pady=(16, 8), sticky="w"
    )

    tk.Label(dlg, text="Username:").grid(row=1, column=0, padx=16, sticky="e")
    username_var = tk.StringVar()
    username_entry = tk.Entry(dlg, textvariable=username_var, width=22)
    username_entry.grid(row=1, column=1, padx=(0, 16), pady=4, sticky="w")

    tk.Label(dlg, text="Password:").grid(row=2, column=0, padx=16, sticky="e")
    password_var = tk.StringVar()
    password_entry = tk.Entry(dlg, textvariable=password_var, show="•", width=22)
    password_entry.grid(row=2, column=1, padx=(0, 16), pady=4, sticky="w")

    btn_frame = tk.Frame(dlg)
    btn_frame.grid(row=3, column=0, columnspan=2, pady=12)

    def on_ok(event=None) -> None:  # noqa: ANN001
        u = username_var.get().strip()
        p = password_var.get()
        if not u or not p:
            messagebox.showwarning("Missing Fields", "Please enter both username and password.", parent=dlg)
            return
        result[0] = (u, p)
        dlg.destroy()

    def on_cancel() -> None:
        dlg.destroy()

    tk.Button(btn_frame, text="OK", width=10, command=on_ok).pack(side="left", padx=8)
    tk.Button(btn_frame, text="Cancel", width=10, command=on_cancel).pack(side="left", padx=8)

    dlg.bind("<Return>", on_ok)
    dlg.bind("<Escape>", lambda _e: on_cancel())
    username_entry.focus_set()

    root.wait_window(dlg)
    root.destroy()
    return result[0]


def prompt_new_password_dialog() -> Optional[str]:
    """
    Show a dialog to enter + confirm a new password.

    Returns the new password string on success, or None on cancel.
    """
    result: list[Optional[str]] = [None]

    root = tk.Tk()
    root.withdraw()

    dlg = tk.Toplevel(root)
    dlg.title("Screen Time Monitor — Change Password")
    dlg.resizable(False, False)
    dlg.grab_set()

    w, h = 340, 180
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    tk.Label(dlg, text="Enter and confirm the new password:", wraplength=300, justify="left").grid(
        row=0, column=0, columnspan=2, padx=16, pady=(16, 8), sticky="w"
    )

    tk.Label(dlg, text="New password:").grid(row=1, column=0, padx=16, sticky="e")
    pw1_var = tk.StringVar()
    tk.Entry(dlg, textvariable=pw1_var, show="•", width=22).grid(
        row=1, column=1, padx=(0, 16), pady=4, sticky="w"
    )

    tk.Label(dlg, text="Confirm:").grid(row=2, column=0, padx=16, sticky="e")
    pw2_var = tk.StringVar()
    tk.Entry(dlg, textvariable=pw2_var, show="•", width=22).grid(
        row=2, column=1, padx=(0, 16), pady=4, sticky="w"
    )

    btn_frame = tk.Frame(dlg)
    btn_frame.grid(row=3, column=0, columnspan=2, pady=12)

    def on_ok(event=None) -> None:  # noqa: ANN001
        p1 = pw1_var.get()
        p2 = pw2_var.get()
        if len(p1) < MIN_PASSWORD_LENGTH:
            messagebox.showwarning(
                "Too Short",
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                parent=dlg,
            )
            return
        if p1 != p2:
            messagebox.showwarning("Mismatch", "Passwords do not match.", parent=dlg)
            return
        result[0] = p1
        dlg.destroy()

    def on_cancel() -> None:
        dlg.destroy()

    tk.Button(btn_frame, text="OK", width=10, command=on_ok).pack(side="left", padx=8)
    tk.Button(btn_frame, text="Cancel", width=10, command=on_cancel).pack(side="left", padx=8)

    dlg.bind("<Return>", on_ok)
    dlg.bind("<Escape>", lambda _e: on_cancel())

    root.wait_window(dlg)
    root.destroy()
    return result[0]
