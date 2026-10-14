"""Internet-mode helper tests (app/internet.py).

All network access is mocked or loopback-local. Nothing here contacts
the real internet, and nothing here claims a relay/signaling server.
"""

import socket
import threading
import urllib.error
from unittest import mock

from app import internet


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_get_public_ip_parses_plain_text():
    with mock.patch("urllib.request.urlopen",
                    return_value=_FakeResp(b"203.0.113.9\n")):
        assert internet.get_public_ip() == "203.0.113.9"


def test_get_public_ip_parses_json_body():
    with mock.patch("urllib.request.urlopen",
                    return_value=_FakeResp(b'{"ip":"198.51.100.7"}')):
        assert internet.get_public_ip() == "198.51.100.7"


def test_get_public_ip_returns_none_on_network_failure():
    with mock.patch("urllib.request.urlopen",
                    side_effect=urllib.error.URLError("no route")):
        assert internet.get_public_ip() is None


def test_get_public_ip_returns_none_on_garbage_body():
    with mock.patch("urllib.request.urlopen",
                    return_value=_FakeResp(b"not-an-ip")):
        assert internet.get_public_ip() is None


def test_upnp_fallback_when_miniupnpc_missing(monkeypatch):
    monkeypatch.setattr(internet, "miniupnpc", None)
    assert internet.upnp_available() is False
    ok, msg = internet.try_upnp_mapping(47900)
    assert ok is False
    assert "miniupnpc not installed" in msg
    assert "manual port forwarding" in msg.lower()


def test_try_upnp_mapping_invalid_port_never_raises():
    ok, msg = internet.try_upnp_mapping("not-a-port")
    assert ok is False
    assert msg


def test_get_lan_ip_returns_string():
    ip = internet.get_lan_ip()
    assert isinstance(ip, str) and ip
    socket.inet_aton(ip)  # must be a parseable IPv4 address


def test_check_port_reachable_open_then_closed_port():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert internet.check_port_reachable("127.0.0.1", port, timeout=1) is True
    finally:
        srv.close()
    assert internet.check_port_reachable("127.0.0.1", port, timeout=1) is False


def test_check_port_reachable_invalid_input_returns_false():
    assert internet.check_port_reachable(None, 47900) is False
    assert internet.check_port_reachable("", 47900) is False
    assert internet.check_port_reachable("256.256.256.256", 47900) is False
    assert internet.check_port_reachable("127.0.0.1", "nope") is False
    assert internet.check_port_reachable("127.0.0.1", 0) is False
