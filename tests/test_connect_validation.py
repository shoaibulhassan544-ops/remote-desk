"""Tests for the v1.0.4 Device-ID connect fix.

A bare 9-digit Device ID in the IP field must be BLOCKED, never
attempted as a connection target. This is the exact bug from the
user's screenshot ("739738074" -> "not found on this LAN").
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.connect_target import (  # noqa: E402
    looks_like_bare_device_id,
    split_host_port,
    validate_connect_input,
)


def test_bare_device_id_blocked_in_ip_field():
    for bad in ("739738074", "739 738 074", " 739738074 "):
        decision = validate_connect_input(bad, "", "lan")
        assert decision["action"] == "error"
        assert "Device ID" in decision["error"]
        assert "IP" in decision["error"]


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


def test_device_id_needs_signaling_url_in_signaling_mode():
    decision = validate_connect_input("", "739738074", "signaling", "")
    assert decision["action"] == "error"
    assert "Settings" in decision["error"]
    decision = validate_connect_input("", "739738074", "signaling",
                                      "https://signal.example.com")
    assert decision["action"] == "signaling_lookup"
    assert decision["device_id"] == "739738074"


def test_device_id_in_lan_mode_goes_to_lan_scan():
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
