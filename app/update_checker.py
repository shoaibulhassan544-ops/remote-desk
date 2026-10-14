"""Update checker — NO server required.

Source of truth: GitHub Releases of UPDATE_REPO (config.py).
The app GETs https://api.github.com/repos/<OWNER>/<REPO>/releases/latest,
compares tag_name (e.g. "v1.1.0") against the running version, and if newer,
returns the release info including download assets.

v1.0.2 change: the update popup downloads the installer IN-APP
(download_update) instead of opening GitHub in the browser. The browser
fallback is kept ONLY for when no Setup installer asset exists or the
in-app download fails.

Google Drive is NOT used for auto-update: Drive has no version API, so it
cannot tell clients a new version exists. Drive is only a manual
share-the-installer link. See docs/SETUP_UPDATE.md.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

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


def select_setup_asset(assets: list | None) -> dict | None:
    """Pick the installer asset from a release's asset list.

    Prefers an asset whose name starts with "Setup-RemoteDesk-" and ends
    with ".exe". Falls back to any ".exe" asset. Returns None when no
    usable asset exists.
    """
    if not assets:
        return None
    for a in assets:
        name = str(a.get("name", ""))
        if name.startswith("Setup-RemoteDesk-") and name.endswith(".exe"):
            return a
    for a in assets:
        name = str(a.get("name", ""))
        if name.endswith(".exe"):
            return a
    return None


def _normalise_assets(raw_assets) -> list:
    out = []
    if not isinstance(raw_assets, list):
        return out
    for a in raw_assets:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name", ""))
        url = str(a.get("browser_download_url", ""))
        if name and url:
            out.append({"name": name, "download_url": url,
                        "size": a.get("size")})
    return out


def check_for_update(url: str = config.UPDATE_CHECK_URL,
                     current: str = VERSION,
                     timeout: float = config.UPDATE_CHECK_TIMEOUT_S) -> dict | None:
    """Return release dict if an update is available, else None.

    Release dict: {"tag", "name", "notes", "url", "assets": [...]} where
    each asset is {"name", "download_url", "size"}.
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
            "assets": _normalise_assets(data.get("assets")),
        }
    except (urllib.error.URLError, ValueError, KeyError, OSError):
        return None


def default_update_dir() -> Path:
    """~/Downloads/RemoteDesk-Updates — where in-app downloads land."""
    return Path.home() / "Downloads" / "RemoteDesk-Updates"


def _safe_filename(name: str) -> str:
    """Strip directory components / unsafe chars from an asset filename."""
    base = os.path.basename(str(name).replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._\-]", "_", base)
    return base or "RemoteDesk-update.exe"


def download_update(asset_url: str, dest_dir=None,
                    progress_callback=None, cancel_event=None):
    """Download an update asset in-app. Never raises.

    Streams via urllib to <dest_dir>/<filename>. progress_callback, when
    given, is called as progress_callback(downloaded_bytes, total_bytes)
    where total_bytes may be 0 when unknown. cancel_event, when given,
    is a threading.Event: if set, the download stops and the partial
    file is removed.

    Returns (path_str, error_str_or_None). On success error is None.
    On failure path is None and error is a short message.
    """
    try:
        if not asset_url:
            return None, "No download link for this update."
        dest = Path(dest_dir) if dest_dir else default_update_dir()
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return None, f"Could not create download folder: {exc}"
        # Filename: last path segment of the URL (asset name), sanitised.
        raw_name = urllib.request.urlparse(asset_url).path.rsplit("/", 1)[-1]
        filename = _safe_filename(urllib.request.unquote(raw_name))
        target = dest / filename
        req = urllib.request.Request(
            asset_url, headers={"User-Agent": "RemoteDesk-Updater"})
        downloaded = 0
        total = 0
        try:
            resp = urllib.request.urlopen(req, timeout=60)
        except Exception as exc:  # network / DNS / 404 / etc.
            return None, f"Download failed: {exc}"
        try:
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0
            with open(target, "wb") as fh:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        fh.close()
                        try:
                            target.unlink()
                        except OSError:
                            pass
                        return None, "Download cancelled."
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        try:
                            progress_callback(downloaded, total)
                        except Exception:
                            pass
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return str(target), None
    except Exception as exc:  # never raise out of the updater
        return None, f"Download failed: {exc}"
