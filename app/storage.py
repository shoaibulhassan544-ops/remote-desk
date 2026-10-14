"""Local persistent storage: settings, trusted devices, session history.

Format: plain JSON files under the app data dir (no database server needed).
Secrets policy:
- Unattended password: stored ONLY as a salted PBKDF2 hash (security.py).
- TLS private key: separate PEM file, 0o600 (security.ensure_tls_cert).
- Trusted-device entries store device ID + name + date, never credentials.
- If `keyring` (OS credential store) is available it is preferred for any
  future reversible secret; this v1 stores no reversible secrets at all.
"""

import json
import os
import time

from . import config

FILES = {
    "settings": "settings.json",
    "trusted": "trusted_devices.json",
    "history": "history.json",
    "audit": "audit.json",
}


def _path(name: str, data_dir: str | None = None) -> str:
    data_dir = data_dir or config.app_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, FILES[name])


def _load(name: str, default, data_dir: str | None = None):
    try:
        with open(_path(name, data_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(name: str, data, data_dir: str | None = None):
    path = _path(name, data_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


DEFAULT_SETTINGS = {
    "theme": "dark",
    "port": config.DEFAULT_PORT,
    "download_dir": config.default_download_dir(),
    "clipboard_sync": False,
    "auto_update_check": True,
    "unattended_enabled": False,
    "unattended_password_hash": "",
    "unattended_allow_control": False,
    "hosting_enabled": False,
    "connection_type": "lan",  # "lan" | "internet" | "signaling" — UI default, saved
    "file_transfer_enabled": True,  # global gate; per-session host Accept still required
    "signaling_url": "",  # empty = signaling OFF; both PCs must use the same URL
    "signaling_auto_register": False,  # register this PC when hosting starts
}

# ------------------------------------------------------------------ settings
def load_settings(data_dir: str | None = None) -> dict:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(_load("settings", {}, data_dir))
    return merged


def save_settings(settings: dict, data_dir: str | None = None):
    _save("settings", settings, data_dir)

# ------------------------------------------------------------------ trusted
def load_trusted(data_dir: str | None = None) -> list[dict]:
    return _load("trusted", [], data_dir)


def add_trusted(device_id: str, device_name: str, note: str = "",
                data_dir: str | None = None, control_allowed: bool = False,
                files_allowed: bool = False) -> list[dict]:
    """Add/replace a trusted device.

    Trust is per-device and revocable (see remove_trusted). Records carry
    the permissions the host granted at trust time, so a later
    one-click trusted connect reuses exactly those permissions.
    """
    devices = [d for d in load_trusted(data_dir) if d.get("device_id") != device_id]
    devices.append({"device_id": device_id, "device_name": device_name,
                    "note": note, "added_at": time.time(),
                    "trusted_at": time.time(),
                    "control_allowed": bool(control_allowed),
                    "files_allowed": bool(files_allowed)})
    _save("trusted", devices, data_dir)
    return devices


def find_trusted(device_id: str, data_dir: str | None = None) -> dict | None:
    """Return the trusted record for a device ID, or None."""
    for d in load_trusted(data_dir):
        if d.get("device_id") == str(device_id):
            return d
    return None


def remove_trusted(device_id: str, data_dir: str | None = None) -> list[dict]:
    devices = [d for d in load_trusted(data_dir) if d.get("device_id") != device_id]
    _save("trusted", devices, data_dir)
    return devices

# ------------------------------------------------------------------ history
def load_history(data_dir: str | None = None) -> list[dict]:
    return _load("history", [], data_dir)


def append_history(entry: dict, data_dir: str | None = None):
    history = load_history(data_dir)
    history.append(entry)
    _save("history", history[-500:], data_dir)  # keep last 500
