"""v1.0.11: Connect must actually work (AnyDesk-like reliability).

Covers the four connect fixes:
1) Subnet-directed broadcast (192.168.1.255) FIRST — Windows drops the
   limited broadcast (255.255.255.255) too often for it to be the only
   target. Listener must bind 0.0.0.0 (all interfaces).
2) Firewall: setup.iss adds a netsh Allow rule at install; firewall.py
   builds the exact command + elevated path.
3) Real connect errors: refused / timeout / TLS / DNS each map to a
   plain-words message naming the cause AND the fix — never a bare
   exception. Device-ID-not-found is a checklist, not a dead end.
4) Connection Test: 4 steps (resolve → TCP → TLS → host jawab),
   each PASS/FAIL, never raises, never freezes the UI (threaded in UI).

Also covers the v1.0.10 build failures (URGENT ADDITION):
- scroll test used the Linux-only <Button-5> event on Windows (fixed:
  platform-aware wheel events in test_scroll_smooth.py).
- list batch mode configured rows per insert (fixed: command= in the
  constructor + dynamic index resolution; test now counts only
  refresh configures — see test_tab_switch_no_rebuild.py).
"""

import os
import re
import socket
import ssl
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config  # noqa: E402
from app.client import classify_connect_error  # noqa: E402
from app.connection_test import run_connection_test  # noqa: E402
from app.connect_target import DEVICE_NOT_FOUND_ERROR  # noqa: E402
from app.discovery import (  # noqa: E402
    DiscoveryBroadcaster,
    DiscoveryListener,
    broadcast_for_ip,
    broadcast_targets,
)
from app.firewall import (  # noqa: E402
    add_firewall_rule,
    add_firewall_rule_elevated,
    firewall_rule_command,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------- 1) discovery
def test_broadcast_for_ip_computes_subnet_broadcast():
    assert broadcast_for_ip("192.168.1.50") == "192.168.1.255"
    assert broadcast_for_ip("10.0.5.7") == "10.0.5.255"
    assert broadcast_for_ip("127.0.0.1") is None  # loopback: no subnet bcast
    assert broadcast_for_ip("not-an-ip") is None
    assert broadcast_for_ip("") is None


def test_broadcast_targets_subnet_first_then_limited_then_loopback():
    targets = broadcast_targets(local_ip_fn=lambda: "192.168.1.50")
    assert targets[0] == ("192.168.1.255", config.DISCOVERY_PORT), \
        "subnet-directed broadcast must go FIRST (most reliable)"
    assert ("<broadcast>", config.DISCOVERY_PORT) in targets
    assert ("127.0.0.1", config.DISCOVERY_PORT) in targets
    assert len(targets) == len(set(targets)), "targets must be deduped"


def test_broadcaster_sends_to_subnet_broadcast():
    class FakeSocket:
        def __init__(self):
            self.sent = []

        def setsockopt(self, *a):
            pass

        def sendto(self, packet, target):
            self.sent.append(target)

        def close(self):
            pass

    fake = FakeSocket()
    b = DiscoveryBroadcaster("739738074", "HostPC", 47900,
                             sock_factory=lambda: fake,
                             local_ip_fn=lambda: "192.168.1.50")
    b.start()
    time.sleep(0.4)
    b.stop()
    b.join(timeout=2.0)
    targets = {t for t in fake.sent}
    assert ("192.168.1.255", config.DISCOVERY_PORT) in targets
    assert ("<broadcast>", config.DISCOVERY_PORT) in targets
    assert ("127.0.0.1", config.DISCOVERY_PORT) in targets


def test_listener_binds_all_interfaces():
    class FakeSocket:
        def __init__(self):
            self.bound = None

        def setsockopt(self, *a):
            pass

        def bind(self, addr):
            self.bound = addr

        def settimeout(self, *a):
            pass

        def recvfrom(self, size):
            raise socket.timeout("none")

        def close(self):
            pass

    fake = FakeSocket()
    DiscoveryListener(duration_s=0.05, sock_factory=lambda: fake).scan()
    assert fake.bound is not None
    host, port = fake.bound
    assert host in ("", "0.0.0.0"), f"listener must bind all interfaces, got {host}"
    assert port == config.DISCOVERY_PORT


# ---------------------------------------------------------- 2) firewall
def test_firewall_rule_command_exact():
    cmd = firewall_rule_command(r"C:\Users\SHOAI-B\AppData\Local\Programs\RemoteDesk\RemoteDesk.exe")
    assert cmd[0] == "netsh"
    assert "advfirewall" in cmd and "firewall" in cmd and "add" in cmd and "rule" in cmd
    assert "name=RemoteDesk" in cmd
    assert "dir=in" in cmd and "action=allow" in cmd and "enable=yes" in cmd
    assert any("RemoteDesk.exe" in part for part in cmd)


def test_firewall_add_rule_reports_plain_words():
    def ok_runner(cmd, **k):
        class R:
            returncode = 0
            stderr = ""
            stdout = "Ok."
        return R()

    ok, msg = add_firewall_rule("C:\\RemoteDesk.exe", runner=ok_runner)
    assert ok and "Allow" in msg

    def denied_runner(cmd, **k):
        class R:
            returncode = 1
            stderr = "Access is denied."
            stdout = ""
        return R()

    ok, msg = add_firewall_rule("C:\\RemoteDesk.exe", runner=denied_runner)
    assert not ok and "admin" in msg.lower()


def test_firewall_elevated_non_windows():
    if sys.platform == "win32":
        return  # covered by the Windows-only path below on real Windows
    ok, msg = add_firewall_rule_elevated("C:\\RemoteDesk.exe")
    assert not ok and "sirf Windows" in msg


def test_firewall_elevated_uses_runas():
    seen = {}

    def fake_shell_exec(op, exe, params):
        seen.update(op=op, exe=exe, params=params)
        return 42  # ShellExecuteW > 32 = success

    import sys as _sys
    orig_platform = _sys.platform
    try:
        # Simulate Windows without actually being on it: the function
        # gates on sys.platform, so monkeypatch it for this check.
        sys.platform = "win32"
        ok, msg = add_firewall_rule_elevated(
            "C:\\RemoteDesk.exe", shell_exec=fake_shell_exec)
    finally:
        _sys.platform = orig_platform
    assert ok
    assert seen["op"] == "runas" and seen["exe"] == "netsh"
    assert "RemoteDesk" in seen["params"]


def test_setup_iss_adds_firewall_rule():
    iss = open(os.path.join(ROOT, "setup.iss"), encoding="utf-8").read()
    run = iss[iss.index("[Run]"):]
    assert "netsh" in run
    assert "advfirewall firewall add rule" in run
    assert 'name=""RemoteDesk""' in run
    assert "RemoteDesk.exe" in run
    assert "runhidden" in run


# --------------------------------------------------- 3) real connect errors
def test_classify_connection_refused():
    msg = classify_connect_error(ConnectionRefusedError(10061, "refused"),
                                 "192.168.1.5", 47900)
    assert "Start Hosting" in msg and "Firewall" in msg


def test_classify_timeout():
    msg = classify_connect_error(TimeoutError("timed out"), "192.168.1.5", 47900)
    assert "timeout" in msg.lower() and "Wi-Fi" in msg


def test_classify_tls():
    msg = classify_connect_error(ssl.SSLError("handshake failure"),
                                 "192.168.1.5", 47900)
    assert "handshake" in msg.lower() and "same version" in msg


def test_classify_dns():
    msg = classify_connect_error(socket.gaierror("Name or service not known"),
                                 "badhost", 47900)
    assert "resolve" in msg.lower()


def test_device_not_found_is_a_checklist():
    assert "Checklist" in DEVICE_NOT_FOUND_ERROR
    assert "Start Hosting" in DEVICE_NOT_FOUND_ERROR
    assert "ek hi Wi-Fi" in DEVICE_NOT_FOUND_ERROR
    assert "Firewall" in DEVICE_NOT_FOUND_ERROR
    assert "Find on LAN" in DEVICE_NOT_FOUND_ERROR
    assert "IP address" in DEVICE_NOT_FOUND_ERROR


# ----------------------------------------------------- 4) connection test
class _FakeRaw:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _all_pass_fns():
    return dict(
        scan_fn=lambda: {"739738074": {"address": "192.168.1.42"}},
        tcp_connect_fn=lambda h, p, t: _FakeRaw(),
        tls_wrap_fn=lambda raw, host: _FakeRaw(),
    )


def test_connection_test_all_pass_device_id():
    results = run_connection_test("739738074", {"port": 47900}, **_all_pass_fns())
    assert [r["status"] for r in results] == ["PASS", "PASS", "PASS", "INFO"]
    assert "192.168.1.42" in results[0]["detail"]
    assert "Accept" in results[3]["detail"]


def test_connection_test_all_pass_direct_ip():
    results = run_connection_test("192.168.1.42", {"port": 47900}, **_all_pass_fns())
    assert [r["status"] for r in results] == ["PASS", "PASS", "PASS", "INFO"]


def test_connection_test_stops_at_failed_resolve():
    results = run_connection_test("739738074", {"port": 47900},
                                  scan_fn=lambda: {},
                                  tcp_connect_fn=lambda h, p, t: _FakeRaw(),
                                  tls_wrap_fn=lambda raw, host: _FakeRaw())
    assert len(results) == 1
    assert results[0]["status"] == "FAIL"
    assert "Checklist" in results[0]["detail"]


def test_connection_test_stops_at_tcp_refused():
    def refused(h, p, t):
        raise ConnectionRefusedError("refused")

    results = run_connection_test("192.168.1.42", {"port": 47900},
                                  tcp_connect_fn=refused,
                                  tls_wrap_fn=lambda raw, host: _FakeRaw())
    assert len(results) == 2
    assert results[1]["status"] == "FAIL"
    assert "Start Hosting" in results[1]["detail"]


def test_connection_test_tls_failure():
    def bad_tls(raw, host):
        raise ssl.SSLError("handshake failure")

    results = run_connection_test("192.168.1.42", {"port": 47900},
                                  tcp_connect_fn=lambda h, p, t: _FakeRaw(),
                                  tls_wrap_fn=bad_tls)
    assert len(results) == 3
    assert results[2]["status"] == "FAIL"
    assert "handshake" in results[2]["detail"].lower()


def test_connection_test_invalid_address_never_raises():
    results = run_connection_test("!!!", {"port": 47900})
    assert len(results) == 1 and results[0]["status"] == "FAIL"


def test_ipv4_with_nine_digits_is_direct_not_device_id():
    """v1.0.11 regression: "192.168.1.42" has exactly 9 digits
    ("192168142") and was misclassified as a Device ID — typing that
    IP made the app do a Device-ID LAN lookup, fail, and show
    "Device ID nahi mila" instead of connecting to the IP. This is
    one real reason the user's IP connect failed."""
    from app.connect_target import classify_address
    assert classify_address("192.168.1.42") == "direct"
    assert classify_address("192.168.0.12") == "direct"  # digits: 192168012
    assert classify_address("10.0.0.5") == "direct"
    assert classify_address("739 738 074") == "device_id"
    assert classify_address("739738074") == "device_id"


def test_connection_test_signaling_fallback():
    def lookup(url, did):
        return ({"ip": "203.0.113.9", "port": 47900}, None)

    results = run_connection_test(
        "739738074", {"port": 47900, "signaling_url": "http://example.invalid"},
        scan_fn=lambda: {}, lookup_fn=lookup,
        tcp_connect_fn=lambda h, p, t: _FakeRaw(),
        tls_wrap_fn=lambda raw, host: _FakeRaw())
    assert results[0]["status"] == "PASS"
    assert "203.0.113.9" in results[0]["detail"]


# ---------------------------------------------------------- version guards
def test_version_is_1_0_11_everywhere():
    from app.version import VERSION
    assert VERSION == "1.0.11"
    iss = open(os.path.join(ROOT, "setup.iss"), encoding="utf-8").read()
    assert '#define MyAppVersion "1.0.11"' in iss
    assert "v1.0.11" in open(os.path.join(
        ROOT, "app", "update_checker.py"), encoding="utf-8").read()


def test_ui_has_connection_test_and_firewall():
    src = open(os.path.join(ROOT, "app", "ui.py"), encoding="utf-8").read()
    assert "Connection Test" in src
    assert "_run_connection_test_for" in src
    assert "Windows Firewall me Allow karo" in src
    assert "_add_firewall_rule" in src
    assert "Hosting ON — Port" in src
    assert "Checklist: 1) Dusre PC pe Start Hosting ON hai?" in src
