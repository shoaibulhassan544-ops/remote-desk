"""Tests for the signaling server (directory) + client.

The server runs in-process on an ephemeral port; the client talks to
it over real HTTP. No network access beyond localhost.
"""

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import signaling  # noqa: E402
from server.signaling_server import Registry, make_handler  # noqa: E402


class _Server:
    def __enter__(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp.close()
        self.data_file = tmp.name
        self.registry = Registry(self.data_file)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.registry))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.port}"
        # v1.0.12: never assume the server is ready just because the
        # thread started — on a slow/loaded CI runner the listener may
        # not be accepting yet. Poll until a TCP connect succeeds
        # (max ~10s); every test in this file inherits the guarantee.
        deadline = time.monotonic() + 10.0
        while True:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1.0):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        try:
            os.unlink(self.data_file)
        except OSError:
            pass


def test_register_lookup_unregister_roundtrip():
    with _Server() as srv:
        ok, _msg = signaling.register_device(srv.url, "123456789", "TEST-PC", 47900)
        assert ok is True
        peer, err = signaling.lookup_device(srv.url, "123 456 789")
        assert err is None
        assert peer["ip"] == "127.0.0.1"
        assert peer["port"] == 47900
        assert peer["device_name"] == "TEST-PC"
        ok, _ = signaling.unregister_device(srv.url, "123456789")
        assert ok is True
        _peer, err = signaling.lookup_device(srv.url, "123456789")
        assert err is not None  # 404 after unregister


def test_lookup_unknown_id_is_404_error_not_crash():
    with _Server() as srv:
        peer, err = signaling.lookup_device(srv.url, "999999999")
        assert peer is None
        assert "nahi mila" in err or "not found" in err.lower()


def test_register_rejects_bad_device_id():
    with _Server() as srv:
        ok, err = signaling.register_device(srv.url, "123", "X", 47900)
        assert ok is False
        assert err


def test_register_rate_limit_429():
    with _Server() as srv:
        ok, _ = signaling.register_device(srv.url, "111222333", "X", 47900)
        assert ok is True
        # Immediate second register for the same ID must be rate-limited.
        ok2, err2 = signaling.register_device(srv.url, "111222333", "X", 47900)
        assert ok2 is False
        assert "Too many" in err2 or "wait" in err2.lower()


def test_client_never_raises_on_dead_server():
    peer, err = signaling.lookup_device("http://127.0.0.1:1", "123456789")
    assert peer is None
    assert err


def test_normalize_server_url():
    assert signaling.normalize_server_url("") == ""
    assert signaling.normalize_server_url("example.com/") == "https://example.com"
    assert signaling.normalize_server_url("http://h:8000") == "http://h:8000"


def test_health_endpoint():
    # v1.0.12: this test flaked on the Windows CI runner with
    # TimeoutError in socket readinto (slow/loaded machine, default-ish
    # 5s timeout, single attempt). It is a timing flake, not a product
    # bug — but a flaky test that blocks shipping is itself a bug.
    # Fix: generous 15s timeout + up to 3 attempts with backoff, on top
    # of _Server's wait-for-listening. Assertion unchanged: /health
    # must return 200 with {"ok": true, "devices": 0}.
    with _Server() as srv:
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                    f"{srv.url}/health", timeout=15
                ) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                break
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise AssertionError(
                    f"/health did not respond after 3 attempts: {exc!r}"
                ) from exc
        assert body["ok"] is True
        assert body["devices"] == 0
