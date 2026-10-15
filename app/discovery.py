"""LAN discovery via UDP broadcast.

A host that has hosting enabled broadcasts a small announcement packet
(device ID + name + port) on DISCOVERY_PORT. Guests listening on the LAN
collect announcements. Discovery advertises PRESENCE ONLY — it never
grants access; a connection still requires host Accept (assisted) or unattended password
and host Accept.

Broadcasts are sent only while hosting is enabled, and only on the LAN.
"""

import ipaddress
import json
import socket
import threading
import time

from . import config


def broadcast_for_ip(ip: str, prefix: int = 24) -> str | None:
    """Subnet-directed broadcast for one local IPv4 address.

    Most home routers use a /24 netmask, so the directed broadcast
    (e.g. 192.168.1.255 for 192.168.1.50/24) is computed with
    ipaddress (stdlib). Returns None for non-IPv4 / loopback input.
    """
    try:
        addr = ipaddress.IPv4Address((ip or "").strip())
    except ValueError:
        return None
    if addr.is_loopback or addr.is_link_local:
        return None
    try:
        net = ipaddress.IPv4Network(f"{addr}/{int(prefix)}", strict=False)
    except ValueError:
        return None
    return str(net.broadcast_address)


def local_ip() -> str:
    """This PC's primary LAN IP via the UDP-socket trick (no packet sent)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0] or "127.0.0.1"
        finally:
            sock.close()
    except OSError:
        return "127.0.0.1"


def broadcast_targets(local_ip_fn=None) -> list[tuple[str, int]]:
    """All UDP targets a presence packet must go to (deduped, in order).

    v1.0.11: sending ONLY to 255.255.255.255 (``<broadcast>``) is NOT
    enough — Windows / many routers drop the limited broadcast, so the
    host's announcements never reached the guest and a Device ID could
    never resolve. The subnet-directed broadcast (e.g. 192.168.1.255)
    is far more reliable, so it goes FIRST, then the limited broadcast,
    then loopback (same-PC discovery).
    """
    targets: list[tuple[str, int]] = []
    try:
        ip = (local_ip_fn or local_ip)()
    except Exception:
        ip = None
    bcast = broadcast_for_ip(ip) if ip else None
    if bcast:
        targets.append((bcast, config.DISCOVERY_PORT))
    targets.append(("<broadcast>", config.DISCOVERY_PORT))
    targets.append(("127.0.0.1", config.DISCOVERY_PORT))
    seen: set[tuple[str, int]] = set()
    out: list[tuple[str, int]] = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def build_announcement(device_id: str, device_name: str, port: int) -> bytes:
    payload = {"magic": "REMOTEDESK-DISCOVERY-v1", "device_id": device_id,
               "device_name": device_name, "port": int(port)}
    return config.DISCOVERY_MAGIC + b"|" + json.dumps(payload).encode("utf-8")


def parse_announcement(data: bytes) -> dict | None:
    try:
        magic, _, body = data.partition(b"|")
        if magic != config.DISCOVERY_MAGIC:
            return None
        obj = json.loads(body.decode("utf-8"))
        if obj.get("magic") != "REMOTEDESK-DISCOVERY-v1":
            return None
        if not str(obj.get("device_id", "")).isdigit():
            return None
        return obj
    except (ValueError, UnicodeDecodeError):
        return None


class DiscoveryBroadcaster(threading.Thread):
    """Broadcasts presence every 3s while hosting. Daemon thread."""

    def __init__(self, device_id: str, device_name: str, port: int,
                 sock_factory=None, local_ip_fn=None):
        super().__init__(daemon=True)
        self.device_id, self.device_name, self.port = device_id, device_name, port
        # sock_factory is dependency injection for tests (default: real
        # UDP socket). Sandboxes that block UDP send can still verify
        # the exact packets/targets via a fake socket.
        self._sock_factory = sock_factory
        # local_ip_fn is dependency injection for tests (default: real
        # local-IP lookup). Lets tests pin the subnet broadcast target.
        self._local_ip_fn = local_ip_fn
        self._stop_event = threading.Event()

    def run(self):
        sock = self._sock_factory() if self._sock_factory else \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        packet = build_announcement(self.device_id, self.device_name, self.port)
        # v1.0.11: broadcast targets = subnet-directed broadcast FIRST
        # (reliable on Windows / home routers), then limited broadcast,
        # then loopback. Sending only to <broadcast> lost announcements.
        targets = broadcast_targets(self._local_ip_fn)
        while not self._stop_event.is_set():
            for target in targets:
                try:
                    sock.sendto(packet, target)
                except OSError:
                    pass
            self._stop_event.wait(3.0)
        sock.close()

    def stop(self):
        self._stop_event.set()


class DiscoveryListener:
    """Listens for announcements for `duration_s`; returns {device_id: info}."""

    def __init__(self, duration_s: float = 5.0, sock_factory=None):
        self.duration_s = duration_s
        self._sock_factory = sock_factory

    def scan(self) -> dict[str, dict]:
        found: dict[str, dict] = {}
        sock = self._sock_factory() if self._sock_factory else \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # Bind to "" = 0.0.0.0: listen on ALL interfaces, so
            # announcements arriving on any NIC (Wi-Fi / Ethernet) are
            # received — never bind to one interface only.
            sock.bind(("", config.DISCOVERY_PORT))
        except OSError:
            return found
        sock.settimeout(0.5)
        deadline = time.time() + self.duration_s
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            info = parse_announcement(data)
            if info:
                info["address"] = addr[0]
                found[info["device_id"]] = info
        sock.close()
        return found
