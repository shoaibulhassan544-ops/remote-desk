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
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import config
from .version import VERSION

# Built-in changelog, keyed by release tag. GitHub Releases created via
# the web UI usually have an EMPTY body, which is why the update popup's
# "What's new" box showed up blank. When a release's notes are empty,
# check_for_update() falls back to the entry here; if there is no entry
# for a tag either, it falls back to a generic line — the box is never
# blank again.
CHANGELOG = {
    "v1.0.1": "• EXE startup crash fix (relative-import bug).\n• Use this version or newer — v1.0.0 EXE does not start.",
    "v1.0.2": "• New premium UI (sidebar, navy + gold theme).\n• Update now downloads inside the app (no GitHub redirect).",
    "v1.0.3": "• Blue reference UI (sidebar, 9 screens).\n• Internet direct mode: public IP + UPnP + port-forward guide.",
    "v1.0.4": "• Device ID fix: IP and Device ID are separate fields.\n• AnyDesk-style signaling server (ID → IP directory).\n• Real logo on app, taskbar, installer and desktop.",
    "v1.0.5": "• Simple flow: Address → Enter → host popup → Accept. No pairing code.\n• Centered update popup with live download progress.\n• Multi-size icon fix (taskbar + desktop logo).",
    "v1.0.6": "• Installer now auto-closes the running app before upgrading —\n  no more “Access is denied / DeleteFile code 5” on update.",
    "v1.0.7": "• FIXED: Address (Device ID) now resolves on LAN — host actually\n  broadcasts its presence, so Find on LAN + Address connect work.\n"
               "• FIXED: mouse clicks now land in the right place (real host\n  screen size is sent with every frame; coordinates are scaled).\n"
               "• FIXED: Control defaults ON in the Accept popup, so clicks\n  work after Accept instead of view-only.\n"
               "• Smaller update popup (Download / Later only), with a\n  built-in changelog so “What’s new” is never empty.\n"
               "• Fresh Option 1 (AnyDesk Blue) UI rebuild.",
    "v1.0.8": "• NEW LOOK: UI rebuilt on CustomTkinter — rounded cards,\n  rounded buttons/entries, real card contrast + depth. Same flows,\n  same security: Address → Accept → control.\n"
               "• Same flows as v1.0.7: no pairing code, host Accept always,\n  unattended (password, opt-in) is the only no-Accept path.",
    "v1.0.9": "• AUTO-INSTALL: after the update downloads, the app closes\n  itself and the installer starts on its own — no manual\n  installer button to press, no more locked-file install errors.\n"
               "• FIXED: “What’s new” no longer shows a GitHub compare link\n  — only the real changelog is shown.\n"
               "• NEW: installer now shows a license agreement (EULA).\n"
               "• Upgrade no longer needs an uninstall first — same install\n  folder every version, app exits before the installer runs.",
    "v1.0.10": "• FIXED: Home tab alignment — equal-height top cards, level\n  Device ID + Copy row, breathing room at card bottoms.\n"
               "• FIXED: lag — tab switches no longer rebuild lists (only\n  the shown page refreshes, and only when data changed).\n"
               "• FIXED: scrolling is smooth — no per-notch re-layout,\n  viewer frames capped at ~15 fps with identical-frame skip.\n"
               "• Sidebar: Idle pill + Light/Dark toggle now share the\n  exact width/padding of the nav buttons; Settings rows aligned\n  into one label column + one control column.",
    "v1.0.11": "• FIXED: Connect — Device ID now resolves via subnet-directed\n  broadcast (192.168.1.255) + limited broadcast + loopback, so LAN\n  discovery survives Windows dropping 255.255.255.255.\n"
               "• FIXED: Windows Firewall — installer adds an Allow rule\n  for RemoteDesk, and Settings → Network has a one-click\n  “Windows Firewall me Allow karo” button (UAC prompt).\n"
               "• NEW: Connection Test button — 4 steps (resolve → TCP →\n  TLS → host jawab) each PASS/FAIL in plain words.\n"
               "• FIXED: IP-connect errors now say the REAL reason\n  (refused / timeout / TLS) + what to fix — no bare exceptions.\n"
               "• Device-ID-not-found is now a checklist, not a dead end.\n"
               "• FIXED (build): v1.0.10's 2 test failures — scroll test\n  now uses the platform's real wheel event; list batch mode no\n  longer reconfigures rows per insert.",
    "v1.0.12": "• FIXED (build): v1.0.11 never shipped — its Actions build failed\n  on ONE flaky test (signaling /health timed out on the slow\n  Windows runner). The test is now timing-robust: wait for the\n  server to listen, 15s timeout, 3 attempts with backoff.\n"
               "• No product change vs v1.0.11 — v1.0.11 is superseded\n  and was never shipped. Ship only v1.0.12+.",
}

GENERIC_CHANGELOG = "Is version me stability + bug fixes."


def sanitize_notes(notes: str | None) -> str:
    """Strip GitHub compare-link junk from release notes. Pure function.

    GitHub auto-appends a "**Full Changelog**: <compare URL>" line to
    release notes, and the v1.0.8 popup showed that bare GitHub URL in
    "What's new" (user screenshot). Sanitize:
    - drop any line containing "Full Changelog", "/compare/", or
      "github.com" (the compare line and any other GitHub URL line);
    - strip remaining markdown link syntax "[text](url)" → "text"
      (keep the readable text, drop the URL);
    - remove any leftover bare github.com URL token;
    - collapse 3+ consecutive blank lines to one blank line.
    Returns "" when nothing readable remains (caller falls back).
    """
    raw = notes or ""
    kept = []
    for line in raw.splitlines():
        low = line.lower()
        if "full changelog" in low or "/compare/" in low or "github.com" in low:
            continue
        # "[text](url)" -> "text" (keep text, drop URL).
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
        # Any leftover bare github.com URL token -> drop the token.
        line = re.sub(r"https?://github\.com/\S*", "", line)
        kept.append(line.rstrip())
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def launch_installer_detached(path: str, platform: str | None = None,
                              popen=None):
    """Launch an installer DETACHED so it survives the app exiting.

    The update flow must close the app BEFORE the installer replaces
    files (otherwise Windows locks RemoteDesk.exe and the upgrade
    fails). A detached child keeps running after our process exits.

    - Windows: Popen(..., creationflags=DETACHED_PROCESS |
      CREATE_NEW_PROCESS_GROUP) — the installer is fully independent.
    - POSIX: Popen(..., start_new_session=True).
    `popen` is injectable for tests (no real process is launched).
    Returns the Popen object (or the mock's return value).
    """
    import subprocess

    plat = platform if platform is not None else sys.platform
    launcher = popen or subprocess.Popen
    if plat.startswith("win"):
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        return launcher([path], creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                        close_fds=True)
    return launcher([path], start_new_session=True)


def resolve_notes(tag: str, notes: str | None) -> str:
    """Release notes with fallback: API body → built-in entry → generic.

    The API body is sanitized first (GitHub compare-link junk removed);
    if nothing readable remains, fall back to the built-in entry.
    Never returns blank. Pure function, fully testable.
    """
    body = sanitize_notes(notes)
    if body:
        return body
    entry = CHANGELOG.get((tag or "").strip())
    if entry:
        return entry
    return GENERIC_CHANGELOG


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
            "notes": resolve_notes(tag, str(data.get("body", ""))),
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
