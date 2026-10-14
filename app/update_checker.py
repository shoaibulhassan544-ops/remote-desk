"""Update checker — NO server required.

Source of truth: GitHub Releases of UPDATE_REPO (config.py).
The app GETs https://api.github.com/repos/<OWNER>/<REPO>/releases/latest,
compares tag_name (e.g. "v1.1.0") against the running version, and if newer,
returns the release info. The UI shows a popup with changelog + buttons:
[Download Update] opens the release page in the browser (the user
downloads + installs the new installer), [Later] dismisses.

Google Drive is NOT used for auto-update: Drive has no version API, so it
cannot tell clients a new version exists. Drive is only a manual
share-the-installer link. See docs/SETUP_UPDATE.md.
"""

import json
import re
import urllib.error
import urllib.request

from . import config
from .version import VERSION


def parse_version(tag: str) -> tuple[int, int, int]:
    """'v1.2.3' / '1.2' -> (1, 2, 3). Raises ValueError on garbage."""
    m = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$", str(tag).strip())
    if not m:
        raise ValueError(f"Not a semantic version: {tag!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def is_newer(latest_tag: str, current: str = VERSION) -> bool:
    """True if latest_tag is a newer semantic version than current."""
    return parse_version(latest_tag) > parse_version(current)


def check_for_update(url: str = config.UPDATE_CHECK_URL,
                     current: str = VERSION,
                     timeout: float = config.UPDATE_CHECK_TIMEOUT_S) -> dict | None:
    """Return release dict if an update is available, else None.

    Release dict: {"tag": "v1.1.0", "name": ..., "notes": ..., "url": ...}
    Returns None on: no update, repo not configured, network error,
    malformed response. Never raises — update checks must never crash the app.
    """
    if config.UPDATE_REPO.startswith("OWNER/"):
        return None  # not configured yet — owner must set UPDATE_REPO
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RemoteDesk-Updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name", ""))
        if not tag or not is_newer(tag, current):
            return None
        return {
            "tag": tag,
            "name": str(data.get("name", tag)),
            "notes": str(data.get("body", ""))[:4000],
            "url": str(data.get("html_url", "")),
        }
    except (urllib.error.URLError, ValueError, KeyError, OSError):
        return None
