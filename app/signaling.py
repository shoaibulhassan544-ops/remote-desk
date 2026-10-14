"""Signaling-server client — the AnyDesk-style ID → IP directory.

What this is: a tiny HTTP JSON directory. A host registers
{device_id, device_name, port} and the server records the IP it saw
the request come from. A controller looks up a Device ID and gets
back {ip, port, device_name}, then connects DIRECTLY to that IP
over the existing TLS + pairing-code session.

What this is NOT:
- NOT a relay: screen / input / file traffic NEVER passes through
  the signaling server. It only hands out the address.
- NOT authentication: the pairing code / unattended password is
  still required, and the host still has to Accept (or have
  unattended access enabled). The server never sees a password.
- NOT private by itself: anyone who knows the server URL can look
  up a registered ID and learn its IP. Run it on a private URL and
  see docs/SIGNALING_DEPLOY.md.

Every function NEVER raises — failures return (None, error) or
(False, error) so the UI can show an actionable message.
"""

import json
import re
import urllib.error
import urllib.request

DEVICE_ID_RE = re.compile(r"^\d{9}$")
DEFAULT_TIMEOUT_S = 5.0


def normalize_server_url(url: str) -> str:
    """'example.com' -> 'https://example.com'; '' -> ''. Strips trailing '/'."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _request(url: str, method: str, payload: dict | None,
             timeout: float) -> tuple[dict | None, str | None]:
    try:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "RemoteDesk-Signaling"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            return None, str(body.get("error") or f"Server error {exc.code}")
        except (ValueError, UnicodeDecodeError, OSError):
            return None, f"Server error {exc.code}"
    except (urllib.error.URLError, OSError, ValueError, UnicodeDecodeError) as exc:
        return None, f"Signaling server se connect nahi hua: {exc}"


def register_device(server_url: str, device_id: str, device_name: str,
                    port: int, timeout: float = DEFAULT_TIMEOUT_S) -> tuple[bool, str]:
    """Register this PC so controllers can find it by Device ID."""
    base = normalize_server_url(server_url)
    if not base:
        return False, "Signaling server URL set nahi hai."
    if not DEVICE_ID_RE.match(device_id or ""):
        return False, "Device ID 9 digits ki honi chahiye."
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False, "Port number sahi nahi hai."
    if not 1 <= port <= 65535:
        return False, "Port 1–65535 ke darmiyan hona chahiye."
    result, error = _request(f"{base}/register", "POST",
                             {"device_id": device_id, "device_name": device_name,
                              "port": port}, timeout)
    if error:
        return False, error
    if result and result.get("ok"):
        return True, "Registered — controllers ab is Device ID se dhoondh sakte hain."
    return False, "Registration fail hui — server ka jawab samajh nahi aaya."


def lookup_device(server_url: str, device_id: str,
                  timeout: float = DEFAULT_TIMEOUT_S) -> tuple[dict | None, str | None]:
    """Look up a Device ID -> {ip, port, device_name} or (None, error)."""
    base = normalize_server_url(server_url)
    if not base:
        return None, "Signaling server URL set nahi hai — Settings me daalo ya Direct IP use karo."
    did = re.sub(r"\D", "", device_id or "")
    if not DEVICE_ID_RE.match(did):
        return None, "Device ID 9 digits ki hoti hai (misal: 739 738 074)."
    result, error = _request(f"{base}/lookup?device_id={did}", "GET", None, timeout)
    if error:
        if "404" in error or "not found" in error.lower():
            return None, ("Device ID signaling server pe nahi mila — check karo host ne "
                           "register kiya hai aur dono PCs wahi server URL use kar rahe hain.")
        return None, error
    peer = (result or {}).get("peer")
    if not peer or not peer.get("ip"):
        return None, ("Device ID signaling server pe nahi mila — check karo host ne "
                       "register kiya hai aur dono PCs wahi server URL use kar rahe hain.")
    return peer, None


def unregister_device(server_url: str, device_id: str,
                      timeout: float = DEFAULT_TIMEOUT_S) -> tuple[bool, str]:
    """Remove this PC from the directory (best effort, never raises)."""
    base = normalize_server_url(server_url)
    if not base:
        return False, "Signaling server URL set nahi hai."
    result, error = _request(f"{base}/unregister", "POST",
                             {"device_id": device_id}, timeout)
    if error:
        return False, error
    return bool(result and result.get("ok")), "Unregistered."
