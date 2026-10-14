"""Internet (direct) mode helpers — honest, NO signaling server, NO relay.

Internet mode in v1.0.3 is plain direct TCP: the controller connects to
the host's PUBLIC IP + port with the existing client.connect() TLS path.
Nothing about the protocol changes. What this module adds:

- get_public_ip(): the host's public IP (for telling the controller).
- get_lan_ip(): this PC's LAN IP (the port-forwarding target).
- try_upnp_mapping(): best-effort UPnP port mapping via miniupnpc.
- check_port_reachable(): honest self-test (True/False only).

Every function NEVER raises — on any failure it returns None / False /
(False, message). The UI reports those failures plainly instead of
claiming connectivity that does not exist.

Limits (stated in the UI and docs, not hidden):
- If UPnP fails AND manual port forwarding is not set, direct Internet
  connections will not get through.
- Strict / CGNAT routers (no public IPv4, no UPnP, no port forwarding)
  need a relay server, which is NOT included in this build.
- There is no signaling server in this build — nothing to "connect to"
  besides the other PC's IP address.
"""

import re
import socket
import urllib.error
import urllib.request

try:
    import miniupnpc  # type: ignore[import-not-found]
except ImportError:  # miniupnpc is optional; manual forwarding still works
    miniupnpc = None

PUBLIC_IP_URL = "https://api.ipify.org"
_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _clean_ip(raw: str | None) -> str | None:
    """Return raw if it is a plausible IPv4 address, else None."""
    if not raw:
        return None
    text = raw.strip()
    # Tolerate a JSON body like {"ip": "1.2.3.4"}.
    if text.startswith("{"):
        m = re.search(r'"ip"\s*:\s*"([^"]+)"', text)
        if m:
            text = m.group(1).strip()
    if not _IPV4_RE.match(text):
        return None
    try:
        socket.inet_aton(text)
    except OSError:
        return None
    return text


def get_public_ip(timeout: float = 5.0) -> str | None:
    """This PC's public IP via api.ipify.org. None on any failure."""
    try:
        req = urllib.request.Request(PUBLIC_IP_URL,
                                     headers={"User-Agent": "RemoteDesk"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _clean_ip(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, UnicodeDecodeError):
        return None


def get_lan_ip() -> str:
    """This PC's LAN IP via the UDP-socket trick. Fallback 127.0.0.1."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0] or "127.0.0.1"
        finally:
            sock.close()
    except OSError:
        return "127.0.0.1"


def upnp_available() -> bool:
    """True only if the miniupnpc package is importable."""
    return miniupnpc is not None


def try_upnp_mapping(port: int, lan_ip: str | None = None,
                     description: str = "RemoteDesk") -> tuple[bool, str]:
    """Try to add a UPnP TCP port mapping for `port`. Never raises.

    Returns (True, message) on success, (False, message) otherwise.
    When miniupnpc is not installed the message says so and points at
    manual port forwarding — it never pretends a mapping exists.
    """
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False, "Invalid port for UPnP mapping."
    if not 1 <= port <= 65535:
        return False, "Port out of range for UPnP mapping."
    if miniupnpc is None:
        return False, ("miniupnpc not installed — manual port forwarding needed "
                       "(router → port forwarding → TCP "
                       f"{port} → this PC's LAN IP).")
    try:
        upnp = miniupnpc.UPnP()
        upnp.discoverdelay = 200
        found = upnp.discover()
        if not found:
            return False, ("No UPnP gateway found on this network — use manual "
                           f"port forwarding (TCP {port}) or stay on LAN.")
        upnp.selectigd()
        target = lan_ip or upnp.lanaddr()
        ok = upnp.addportmapping(port, "TCP", target, port, description, "")
        if ok:
            return True, (f"UPnP mapping added: public TCP {port} → "
                          f"{target}:{port}.")
        return False, ("UPnP gateway refused the mapping — use manual port "
                       f"forwarding (TCP {port} → {target}).")
    except Exception as exc:  # noqa: BLE001 — UPnP must never crash the app
        return False, f"UPnP failed: {exc}"


def check_port_reachable(public_ip: str | None, port: int,
                         timeout: float = 3.0) -> bool:
    """Self-test: can this PC TCP-connect to (public_ip, port)?

    Returns True only on a successful connect. Any failure — timeout,
    refused, DNS, invalid input — is False. Note this is a self-test
    from the same PC: some routers fail it even when forwarding works
    for outside callers, so a False here means "not proven reachable",
    not "definitely blocked".
    """
    if not public_ip:
        return False
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False
    if not 1 <= port <= 65535:
        return False
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        return sock.connect_ex((public_ip, port)) == 0
    except (OSError, ValueError):
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass
