"""Bug A (v1.0.7): the host NEVER broadcast its presence, so LAN discovery
found nothing and a Device ID (Address) could never resolve on LAN.

- HostServer.start() must start a DiscoveryBroadcaster.
- HostServer.stop() must stop it (guarded, idempotent).
- A DiscoveryListener scan must actually find the running host.

NOTE on the sandbox: this Linux sandbox blocks UDP *send* (sendto ->
PermissionError), so a real-UDP end-to-end test cannot pass here — it
skips with a clear reason when UDP send is blocked (it still runs on
real Windows / GitHub Actions, where UDP works). The packet contents,
targets, and listener parsing are proven deterministically with fake
sockets (sock_factory injection) below.
"""

import os
import socket
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config  # noqa: E402
from app.discovery import (  # noqa: E402
    DiscoveryBroadcaster,
    DiscoveryListener,
    build_announcement,
    parse_announcement,
)
from app.host import HostServer  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _udp_send_allowed() -> bool:
    """Probe: can this environment send a UDP packet at all?"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(b"probe", ("127.0.0.1", config.DISCOVERY_PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def test_host_broadcasts_and_listener_finds_it():
    """Real-UDP end to end. Skips where the sandbox blocks UDP send."""
    if not _udp_send_allowed():
        pytest.skip("sandbox blocks UDP send (sendto -> EPERM); "
                    "fake-socket tests below prove the same logic")
    port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        host = HostServer("739738074", "HostPC", port, {}, data_dir=tmp,
                          on_request=lambda peer: (False, False, False),
                          on_log=lambda m: None)
        host.start()
        try:
            assert host._broadcaster is not None
            # Broadcaster sends every 3s; scan long enough to catch ≥1 packet.
            found = DiscoveryListener(duration_s=4.0).scan()
            assert "739738074" in found, f"host not found in scan: {found}"
            info = found["739738074"]
            assert info.get("device_name") == "HostPC"
            assert info.get("address"), "announcement must carry the host IP"
        finally:
            host.stop()
            # stop() is idempotent and must not raise on a second call.
            host.stop()
            assert host._broadcaster is None


class _FakeSocket:
    """Records sendto targets; replays one packet then times out."""

    def __init__(self, recv_packets=None):
        self.sent = []
        self._recv = list(recv_packets or [])
        self.closed = False

    def setsockopt(self, *a):
        pass

    def settimeout(self, *a):
        pass

    def bind(self, *a):
        pass

    def sendto(self, packet, target):
        self.sent.append((packet, target))

    def recvfrom(self, size):
        if self._recv:
            return self._recv.pop(0)
        raise socket.timeout("no more packets")

    def close(self):
        self.closed = True


def test_broadcaster_sends_to_broadcast_and_loopback():
    """Deterministic (fake socket): the exact packet goes to BOTH the LAN
    broadcast address AND loopback, so same-PC discovery works even
    where broadcast packets never loop back."""
    fake = _FakeSocket()
    b = DiscoveryBroadcaster("739738074", "HostPC", 47900,
                             sock_factory=lambda: fake)
    b.start()
    time.sleep(0.4)  # first packet is sent immediately at loop start
    b.stop()
    b.join(timeout=2.0)
    assert fake.sent, "broadcaster sent nothing"
    targets = {t for _pkt, t in fake.sent}
    assert ("<broadcast>", config.DISCOVERY_PORT) in targets
    assert ("127.0.0.1", config.DISCOVERY_PORT) in targets
    for packet, _t in fake.sent:
        info = parse_announcement(packet)
        assert info is not None
        assert info["device_id"] == "739738074"
        assert info["device_name"] == "HostPC"
        assert info["port"] == 47900


def test_listener_parses_announcement_with_address():
    """Deterministic (fake socket): listener turns a raw packet into
    {device_id: info} with the sender's address attached."""
    packet = build_announcement("739738074", "HostPC", 47900)
    fake = _FakeSocket(recv_packets=[(packet, ("192.168.1.42", 50000))])
    found = DiscoveryListener(duration_s=0.3,
                              sock_factory=lambda: fake).scan()
    assert "739738074" in found
    assert found["739738074"]["device_name"] == "HostPC"
    assert found["739738074"]["address"] == "192.168.1.42"
    assert found["739738074"]["port"] == 47900


def test_announcement_roundtrip_and_rejects_garbage():
    assert parse_announcement(build_announcement("123", "PC", 1))["device_id"] == "123"
    assert parse_announcement(b"garbage") is None
    assert parse_announcement(b"REMOTEDESK-DISCOVERY-v1|not-json") is None


def test_broadcaster_failure_does_not_kill_hosting():
    # Hosting must still start even if the broadcaster cannot start
    # (e.g. broadcast blocked). Simulate by monkeypatching start to raise.
    import app.host as host_mod
    orig = host_mod.DiscoveryBroadcaster
    logs: list = []

    class BrokenBroadcaster:
        def __init__(self, *a, **k):
            raise OSError("broadcast blocked")

    host_mod.DiscoveryBroadcaster = BrokenBroadcaster
    try:
        port = _free_port()
        with tempfile.TemporaryDirectory() as tmp:
            host = HostServer("111222333", "HostPC", port, {}, data_dir=tmp,
                              on_request=lambda peer: (False, False, False),
                              on_log=logs.append)
            host.start()
            try:
                assert host._thread is not None and host._thread.is_alive()
                assert host._broadcaster is None
            finally:
                host.stop()
    finally:
        host_mod.DiscoveryBroadcaster = orig
    assert any("broadcast" in str(m).lower() for m in logs)
