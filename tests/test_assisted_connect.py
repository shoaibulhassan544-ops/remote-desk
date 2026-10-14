"""Tests for the FINAL v1.0.5 assisted flow.

- Assisted: Address -> request -> host Accept popup decides. NO pairing
  code, NO auto-accept (not even for trusted devices).
- Trusted Devices = address book only.
- Unattended (password, opt-in) is the ONLY no-Accept path.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import storage  # noqa: E402
from app.host import HostServer  # noqa: E402


def _host(tmp, **settings):
    base = {"auto_accept_trusted": False}
    base.update(settings)
    return HostServer("111222333", "HostPC", 47900, base, data_dir=tmp)


def test_request_method_passes_auth():
    with tempfile.TemporaryDirectory() as tmp:
        host = _host(tmp)
        ok, _ = host._check_auth({"method": "request", "device_id": "739738074"})
        assert ok is True


def test_trusted_method_is_rejected_no_auto_accept():
    with tempfile.TemporaryDirectory() as tmp:
        # Even a "trusted" record must NOT auto-accept.
        storage.add_trusted("739738074", "GuestPC", data_dir=tmp)
        host = _host(tmp)
        ok, _ = host._check_auth({"method": "trusted",
                                  "device_id": "739738074"}, "739738074")
        assert ok is False


def test_unknown_auth_method_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        host = _host(tmp)
        ok, _ = host._check_auth({"method": "magic"}, "739738074")
        assert ok is False


def test_unattended_needs_password_and_opt_in():
    with tempfile.TemporaryDirectory() as tmp:
        host = _host(tmp)
        ok, _ = host._check_auth({"method": "unattended", "password": "x"})
        assert ok is False  # not enabled


def test_unattended_password_verified():
    import app.security as security
    with tempfile.TemporaryDirectory() as tmp:
        pw = "correct-horse-99"
        host = _host(tmp, unattended_enabled=True,
                     unattended_password_hash=security.hash_password(pw))
        ok, _ = host._check_auth({"method": "unattended", "password": pw})
        assert ok is True
        ok, _ = host._check_auth({"method": "unattended", "password": "wrong"})
        assert ok is False


def test_trusted_store_is_address_book_only():
    with tempfile.TemporaryDirectory() as tmp:
        storage.add_trusted("739738074", "GuestPC", data_dir=tmp)
        rec = storage.find_trusted("739738074", tmp)
        assert rec is not None
        storage.remove_trusted("739738074", tmp)
        assert storage.find_trusted("739738074", tmp) is None
