"""Connect-target validation — the fix for the "Device ID does not connect" bug.

Root cause (v1.0.3 and earlier): the Connect box was labelled
"Device ID or IP", but a 9-digit Device ID can NEVER resolve to an
address without a directory. The app silently treated the ID as a
hostname / LAN-scan key, and on a different network the user only got
"not found on this LAN" with no way forward.

Rules enforced here (pure functions, no UI, no network — fully testable):
- A bare 9-digit number (with or without spaces, e.g. "739738074" or
  "739 738 074") in the IP field is REJECTED, never attempted as a
  connection target. The caller must show the blocking error.
- The IP field accepts: IPv4, a hostname, or "host:port".
- The Device ID field is reference-only unless the connection mode is
  "signaling", in which case the UI resolves it via the signaling
  server (app/signaling.py). In "lan"/"internet" modes a Device ID
  alone resolves only via a LAN scan (same network).
"""

import re

IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-.]*$")
DEVICE_ID_RE = re.compile(r"^\d{9}$")

BARE_ID_ERROR = (
    "Ye Device ID hai, IP address nahi. IP likho, ya LAN Scan se device "
    "dhoondho, ya Signaling Server lagao (Settings me) taake ID se connect ho."
)
NO_SIGNALING_URL_ERROR = (
    "Signaling server URL set nahi hai — Settings me daalo ya Direct IP use karo."
)


def digits_only(text: str) -> str:
    """Strip everything except digits: '739 738 074' -> '739738074'."""
    return re.sub(r"\D", "", text or "")


def looks_like_bare_device_id(text: str) -> bool:
    """True if `text` is just a 9-digit Device ID (spaces allowed)."""
    return bool(DEVICE_ID_RE.match(digits_only(text or "")))


def looks_like_ipv4(text: str) -> bool:
    return bool(IPV4_RE.match((text or "").strip()))


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


def validate_connect_input(ip_text: str, device_id_text: str, mode: str,
                           signaling_url: str = "") -> dict:
    """Decide what the Connect button should do.

    Returns a dict with keys:
      action: "direct" | "lan_scan" | "signaling_lookup" | "error"
      host:   connectable host for "direct" (else None)
      port:   port parsed from "host:port" in the IP field (else None)
      device_id: normalised 9-digit ID for lookup actions (else "")
      error:  user-facing message for "error" (else "")
    Never raises.
    """
    ip_text = (ip_text or "").strip()
    device_id_text = (device_id_text or "").strip()
    mode = (mode or "lan").strip()
    signaling_url = (signaling_url or "").strip()
    try:
        if ip_text and looks_like_bare_device_id(ip_text):
            return {"action": "error", "host": None, "port": None,
                    "device_id": "", "error": BARE_ID_ERROR}
        if ip_text:
            host, port = split_host_port(ip_text)
            if looks_like_ipv4(host) or HOSTNAME_RE.match(host):
                return {"action": "direct", "host": host, "port": port,
                        "device_id": "", "error": ""}
            return {"action": "error", "host": None, "port": None, "device_id": "",
                    "error": "IP address ya hostname sahi nahi hai — misal: 192.168.1.100"}
        # No IP — fall back to the Device ID field.
        if not device_id_text:
            return {"action": "error", "host": None, "port": None, "device_id": "",
                    "error": "Remote IP address likho, ya Device ID + Signaling Server use karo."}
        did = digits_only(device_id_text)
        if len(did) != 9:
            return {"action": "error", "host": None, "port": None, "device_id": "",
                    "error": "Device ID 9 digits ki hoti hai (misal: 739 738 074). "
                             "IP se connect karne ke liye Remote IP address likho."}
        if mode == "signaling":
            if not signaling_url:
                return {"action": "error", "host": None, "port": None,
                        "device_id": did, "error": NO_SIGNALING_URL_ERROR}
            return {"action": "signaling_lookup", "host": None, "port": None,
                    "device_id": did, "error": ""}
        # LAN / Internet-direct modes: only a LAN scan can resolve an ID.
        return {"action": "lan_scan", "host": None, "port": None,
                "device_id": did, "error": ""}
    except Exception:  # noqa: BLE001 — validation must never crash the UI
        return {"action": "error", "host": None, "port": None, "device_id": "",
                "error": "Connect input samajh nahi aaya — IP address likh kar dobara try karo."}
