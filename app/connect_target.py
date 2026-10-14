"""Connect-target validation + Device-ID auto-resolve (v1.0.5, AnyDesk-simple).

Home has ONE "Remote Address" box. The user types either an IP/hostname
or a 9-digit Device ID — the app figures out the rest:

- IPv4 / hostname / "host:port" -> direct connect.
- 9-digit Device ID -> "auto_resolve": FIRST try LAN discovery (same
  Wi-Fi), then the signaling server (if a URL is configured). If
  neither resolves it, ONE simple error — never jargon about
  "reference-only" IDs or "IP required".

Pure functions where possible (no UI, fully testable). The actual
network resolve lives in resolve_device_id() with injectable
scan/lookup functions so tests can mock them.
"""

import re

IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-.]*$")
DEVICE_ID_RE = re.compile(r"^\d{9}$")

DEVICE_NOT_FOUND_ERROR = (
    "Ye Device ID same Wi-Fi pe nahi mila. Us PC ka IP address likho, "
    "ya Settings me Signaling Server lagao."
)
NO_SIGNALING_URL_ERROR = (
    "Signaling server URL set nahi hai — Settings me daalo ya Direct IP use karo."
)
EMPTY_INPUT_ERROR = "Remote Address likho — Device ID ya IP address."


def digits_only(text: str) -> str:
    """Strip everything except digits: '739 738 074' -> '739738074'."""
    return re.sub(r"\D", "", text or "")


def looks_like_bare_device_id(text: str) -> bool:
    """True if `text` is just a 9-digit Device ID (spaces allowed)."""
    return bool(DEVICE_ID_RE.match(digits_only(text or "")))


def looks_like_ipv4(text: str) -> bool:
    return bool(IPV4_RE.match((text or "").strip()))


def classify_address(text: str) -> str:
    """'direct' | 'device_id' | 'invalid' for one Remote Address input."""
    text = (text or "").strip()
    if not text:
        return "invalid"
    if looks_like_bare_device_id(text):
        return "device_id"
    host, _ = split_host_port(text)
    if looks_like_ipv4(host) or HOSTNAME_RE.match(host):
        return "direct"
    return "invalid"


def split_host_port(text: str) -> tuple[str, int | None]:
    """'192.168.1.5:47900' -> ('192.168.1.5', 47900); 'host' -> ('host', None)."""
    text = (text or "").strip()
    if ":" in text and text.count(":") == 1:
        host, _, port = text.partition(":")
        try:
            return host.strip(), int(port.strip())
        except ValueError:
            return text, None
    return text, None


def resolve_device_id(device_id: str, signaling_url: str = "",
                      scan_fn=None, lookup_fn=None) -> tuple[str | None, int | None, str | None]:
    """Resolve a 9-digit Device ID to (host, port, error).

    1) LAN discovery scan (same Wi-Fi) via scan_fn() -> {did: {"address": ip}}.
    2) Signaling lookup via lookup_fn(url, did) -> (peer_dict, error).
    Returns (host, port, None) on success, (None, None, error) otherwise.
    Never raises.
    """
    did = digits_only(device_id)
    try:
        if scan_fn is not None:
            try:
                found = scan_fn() or {}
            except Exception:
                found = {}
            info = found.get(did) or {}
            if info.get("address"):
                return info["address"], None, None
        url = (signaling_url or "").strip()
        if url and lookup_fn is not None:
            try:
                peer, error = lookup_fn(url, did)
            except Exception:
                peer, error = None, "Signaling server se jawab nahi mila."
            if peer and peer.get("ip"):
                try:
                    return peer["ip"], int(peer.get("port") or 0) or None, None
                except (TypeError, ValueError):
                    return peer["ip"], None, None
            if error:
                return None, None, error
        return None, None, DEVICE_NOT_FOUND_ERROR
    except Exception:  # noqa: BLE001 — resolve must never crash the UI
        return None, None, DEVICE_NOT_FOUND_ERROR


def validate_connect_input(ip_text: str, device_id_text: str, mode: str,
                           signaling_url: str = "") -> dict:
    """Decide what the Connect button should do.

    `ip_text` is the single Remote Address box (Home) or the IP box
    (Remote Control). `device_id_text` is the Remote Control Device ID
    box ("" on Home).

    Returns dict: action ("direct" | "auto_resolve" | "lan_scan" |
    "signaling_lookup" | "error"), host, port, device_id, error.
    A bare 9-digit ID is NO LONGER blocked — it becomes "auto_resolve".
    Never raises.
    """
    address = (ip_text or "").strip()
    device_id_text = (device_id_text or "").strip()
    mode = (mode or "lan").strip()
    signaling_url = (signaling_url or "").strip()
    try:
        if address:
            kind = classify_address(address)
            if kind == "direct":
                host, port = split_host_port(address)
                return {"action": "direct", "host": host, "port": port,
                        "device_id": "", "error": ""}
            if kind == "device_id":
                return {"action": "auto_resolve", "host": None, "port": None,
                        "device_id": digits_only(address), "error": ""}
            return {"action": "error", "host": None, "port": None, "device_id": "",
                    "error": "Address sahi nahi hai — Device ID (misal 739 738 074) "
                             "ya IP address (misal 192.168.1.100) likho."}
        # No address — fall back to the Device ID box (Remote Control page).
        if not device_id_text:
            return {"action": "error", "host": None, "port": None, "device_id": "",
                    "error": EMPTY_INPUT_ERROR}
        did = digits_only(device_id_text)
        if len(did) != 9:
            return {"action": "error", "host": None, "port": None, "device_id": "",
                    "error": "Device ID 9 digits ki hoti hai (misal: 739 738 074)."}
        if mode == "signaling":
            if not signaling_url:
                return {"action": "error", "host": None, "port": None,
                        "device_id": did, "error": NO_SIGNALING_URL_ERROR}
            return {"action": "signaling_lookup", "host": None, "port": None,
                    "device_id": did, "error": ""}
        return {"action": "lan_scan", "host": None, "port": None,
                "device_id": did, "error": ""}
    except Exception:  # noqa: BLE001 — validation must never crash the UI
        return {"action": "error", "host": None, "port": None, "device_id": "",
                "error": "Connect input samajh nahi aaya — Address likh kar dobara try karo."}


# Back-compat: old name, kept so older imports don't break.
BARE_ID_ERROR = DEVICE_NOT_FOUND_ERROR
