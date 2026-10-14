"""LAN discovery via UDP broadcast.

A host that has hosting enabled broadcasts a small announcement packet
(device ID + name + port) on DISCOVERY_PORT. Guests listening on the LAN
collect announcements. Discovery advertises PRESENCE ONLY — it never
grants access; a connection still requires host Accept (assisted) or unattended password
and host Accept.

Broadcasts are sent only while hosting is enabled, and only on the LAN.
"""

import json
import socket
import threading
import time

from . import config


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
                 sock_factory=None):
        super().__init__(daemon=True)
        self.device_id, self.device_name, self.port = device_id, device_name, port
        # sock_factory is dependency injection for tests (default: real
        # UDP socket). Sandboxes that block UDP send can still verify
        # the exact packets/targets via a fake socket.
        self._sock_factory = sock_factory
        self._stop_event = threading.Event()

    def run(self):
        sock = self._sock_factory() if self._sock_factory else \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        packet = build_announcement(self.device_id, self.device_name, self.port)
        # v1.0.7: broadcast alone is NOT enough. On some machines /
        # sandboxes a broadcast packet never loops back to a listener on
        # the SAME PC, so same-PC discovery (and tests) saw nothing even
        # though the broadcaster was running. Send to the LAN broadcast
        # AND to loopback — presence-only either way, no access granted.
        targets = [("<broadcast>", config.DISCOVERY_PORT),
                   ("127.0.0.1", config.DISCOVERY_PORT)]
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
