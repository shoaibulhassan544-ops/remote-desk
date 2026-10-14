"""LAN discovery via UDP broadcast.

A host that has hosting enabled broadcasts a small announcement packet
(device ID + name + port) on DISCOVERY_PORT. Guests listening on the LAN
collect announcements. Discovery advertises PRESENCE ONLY — it never
grants access; a connection still requires pairing-code / unattended auth
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

    def __init__(self, device_id: str, device_name: str, port: int):
        super().__init__(daemon=True)
        self.device_id, self.device_name, self.port = device_id, device_name, port
        self._stop = threading.Event()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        packet = build_announcement(self.device_id, self.device_name, self.port)
        while not self._stop.is_set():
            try:
                sock.sendto(packet, ("<broadcast>", config.DISCOVERY_PORT))
            except OSError:
                pass
            self._stop.wait(3.0)
        sock.close()

    def stop(self):
        self._stop.set()


class DiscoveryListener:
    """Listens for announcements for `duration_s`; returns {device_id: info}."""

    def __init__(self, duration_s: float = 5.0):
        self.duration_s = duration_s

    def scan(self) -> dict[str, dict]:
        found: dict[str, dict] = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
