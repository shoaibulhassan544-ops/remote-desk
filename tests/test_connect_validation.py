"""Tests for the v1.0.5 AnyDesk-simple connect flow.

A bare 9-digit Device ID is NO LONGER blocked (v1.0.4 behaviour) — it
becomes "auto_resolve": LAN scan first, then signaling server, else
ONE simple error. The old "IP required / reference-only" jargon is gone.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.connect_target import (  # noqa: E402
    classify_address,
    looks_like_bare_device_id,
    resolve_device_id,
    split_host_port,
    validate_connect_input,
)


def test_bare_device_id_auto_resolves_not_blocked():
    for text in ("739738074", "739 738 074", " 739738074 "):
        decision = validate_connect_input(text, "", "lan")
        assert decision["action"] == "auto_resolve"
        assert decision["device_id"] == "739738074"
        assert decision["error"] == ""


def test_classify_address():
    assert classify_address("739738074") == "device_id"
    assert classify_address("739 738 074") == "device_id"
    assert classify_address("192.168.1.100") == "direct"
    assert classify_address("192.168.1.100:47900") == "direct"
    assert classify_address("my-pc.local") == "direct"
    assert classify_address("") == "invalid"
    assert classify_address("!!!") == "invalid"


def test_looks_like_bare_device_id():
    assert looks_like_bare_device_id("739738074") is True
    assert looks_like_bare_device_id("739 738 074") is True
    assert looks_like_bare_device_id("192.168.1.100") is False
    assert looks_like_bare_device_id("73973807") is False  # 8 digits
    assert looks_like_bare_device_id("DESKTOP-ABC") is False


def test_ip_field_direct():
    decision = validate_connect_input("192.168.1.100", "", "lan")
    assert decision["action"] == "direct"
    assert decision["host"] == "192.168.1.100"
    assert decision["port"] is None


def test_ip_field_with_port():
    decision = validate_connect_input("192.168.1.100:47900", "", "lan")
    assert decision["action"] == "direct"
    assert decision["host"] == "192.168.1.100"
    assert decision["port"] == 47900


def test_hostname_direct():
    decision = validate_connect_input("my-pc.local", "", "lan")
    assert decision["action"] == "direct"
    assert decision["host"] == "my-pc.local"


def test_resolve_device_id_lan_first():
    scan = lambda: {"739738074": {"address": "192.168.1.50", "device_name": "PC"}}
    host, port, error = resolve_device_id("739738074", "", scan_fn=scan)
    assert host == "192.168.1.50"
    assert error is None


def test_resolve_device_id_signaling_fallback():
    scan = lambda: {}
    lookup = lambda url, did: ({"ip": "203.0.113.9", "port": 47900}, None)
    host, port, error = resolve_device_id(
        "739738074", "https://signal.example.com", scan_fn=scan, lookup_fn=lookup)
    assert host == "203.0.113.9"
    assert port == 47900
    assert error is None


def test_resolve_device_id_neither_gives_simple_error():
    host, port, error = resolve_device_id("739738074", "", scan_fn=lambda: {})
    assert host is None
    assert error is not None
    assert "same Wi-Fi" in error
    assert "reference" not in error.lower()


def test_device_id_box_signaling_mode_still_works():
    decision = validate_connect_input("", "739738074", "signaling", "")
    assert decision["action"] == "error"
    assert "Settings" in decision["error"]
    decision = validate_connect_input("", "739738074", "signaling",
                                      "https://signal.example.com")
    assert decision["action"] == "signaling_lookup"
    assert decision["device_id"] == "739738074"


def test_device_id_box_lan_mode_goes_to_lan_scan():
    decision = validate_connect_input("", "739738074", "lan")
    assert decision["action"] == "lan_scan"
    assert decision["device_id"] == "739738074"


def test_empty_input_is_error():
    decision = validate_connect_input("", "", "lan")
    assert decision["action"] == "error"


def test_short_device_id_is_error():
    decision = validate_connect_input("", "12345", "signaling", "https://x.example")
    assert decision["action"] == "error"


def test_split_host_port():
    assert split_host_port("192.168.1.5:47900") == ("192.168.1.5", 47900)
    assert split_host_port("host") == ("host", None)
    assert split_host_port("host:notaport") == ("host:notaport", None)
