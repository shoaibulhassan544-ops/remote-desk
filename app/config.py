"""Central configuration. No secrets live here — ever.

Product name is TEMPORARY and rebrandable by the owner.
Update source is GitHub Releases (no server owned by Shoaib required).
UPDATE_REPO is "shoaibulhassan544-ops/remote-desk" (public repo; required for the no-server update check).
See docs/SETUP_UPDATE.md for the publish flow.
"""

import os

# --- Product identity (temporary, rebrandable) ---
PRODUCT_NAME = "RemoteDesk"
DEVELOPER_CREDIT = "Developed by Shoaib Azeez"
ABOUT_TEXT = (
    "RemoteDesk is an authorized remote-assistance tool for managing your own "
    "computers and helping people who explicitly accept your connection request.\n\n"
    "Every session requires Accept on the host side. Unattended access is "
    "opt-in, password-protected, and revocable. There is no hidden access."
)

# --- Networking ---
DEFAULT_PORT = 47900
DISCOVERY_PORT = 47901
DISCOVERY_MAGIC = b"REMOTEDESK-DISCOVERY-v1"
HOST = "0.0.0.0"
CONNECT_TIMEOUT_S = 10
FRAME_MAX_BYTES = 8 * 1024 * 1024  # 8 MB per protocol frame (screen frame cap)

# --- Pairing / auth ---
PAIRING_CODE_LENGTH = 6
PAIRING_CODE_TTL_S = 300          # 5 minutes
PAIRING_MAX_ATTEMPTS = 5
PAIRING_LOCKOUT_S = 300           # 5-minute lockout after max attempts
UNATTENDED_MIN_PASSWORD_LEN = 10
SESSION_TTL_S = 8 * 3600           # sessions expire after 8 hours

# --- Screen streaming ---
DEFAULT_JPEG_QUALITY = 70
DEFAULT_FPS = 10
MIN_JPEG_QUALITY = 30
MAX_JPEG_QUALITY = 90

# --- File transfer ---
TRANSFER_CHUNK_SIZE = 64 * 1024   # 64 KiB
MAX_TRANSFER_FILE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB cap
DEFAULT_DOWNLOAD_DIRNAME = "RemoteDesk Received"

# --- Updates (no server required — GitHub Releases is the source) ---
# Public repo: the in-app updater calls the public GitHub Releases API without auth.
UPDATE_REPO = "shoaibulhassan544-ops/remote-desk"
UPDATE_CHECK_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_CHECK_TIMEOUT_S = 10
UPDATE_CHECK_INTERVAL_S = 24 * 3600  # at most once per day automatically

# --- Storage ---
def app_data_dir() -> str:
    """Per-user app data directory (Windows: %APPDATA%/RemoteDesk)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return os.path.join(base, "RemoteDesk")


def default_download_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Downloads", DEFAULT_DOWNLOAD_DIRNAME)
