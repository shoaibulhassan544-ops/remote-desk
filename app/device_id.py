"""Stable device identity: a random device ID + the OS device name.

The ID is generated once and persisted to disk (see storage.py).
It is NOT derived from hardware fingerprints and contains no personal data.
"""

import json
import os
import platform
import secrets
import string

from . import config

_ALPHABET = string.digits  # numeric ID, like AnyDesk-style IDs
ID_LENGTH = 9


def generate_device_id() -> str:
    """Generate a new 9-digit device ID (grouped as XXX XXX XXX in the UI)."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(ID_LENGTH))


def format_device_id(device_id: str) -> str:
    """'123456789' -> '123 456 789' for display."""
    d = "".join(ch for ch in device_id if ch.isdigit())
    return " ".join(d[i:i + 3] for i in range(0, len(d), 3))


def get_device_name() -> str:
    return platform.node() or "Unknown-PC"


def load_or_create_device_id(data_dir: str | None = None) -> str:
    """Load the persisted device ID, or generate + persist a new one."""
    data_dir = data_dir or config.app_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "device.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            did = str(data.get("device_id", "")).strip()
            if did.isdigit() and len(did) == ID_LENGTH:
                return did
        except (OSError, ValueError):
            pass  # corrupt file -> regenerate below
    did = generate_device_id()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"device_id": did, "device_name": get_device_name()}, f)
    os.replace(tmp, path)
    return did
