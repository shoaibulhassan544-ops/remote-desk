"""Pairing-code tests: expiry, single-use, attempt limiting, lockout."""

import time

from app.security import PairingCodeStore


def _store():
    now = [1000.0]
    return PairingCodeStore(_now=lambda: now[0]), now


def test_correct_code_accepted_once():
    store, now = _store()
    code = store.issue()
    assert len(code) == 6 and code.isdigit()
    ok, _ = store.verify(code)
    assert ok is True
    ok2, _ = store.verify(code)  # single use
    assert ok2 is False


def test_wrong_code_rejected():
    store, now = _store()
    store.issue()
    ok, reason = store.verify("000000")
    assert ok is False
    assert "Incorrect" in reason


def test_expired_code_rejected():
    store, now = _store()
    code = store.issue()
    now[0] += 301  # past 5-minute TTL
    ok, reason = store.verify(code)
    assert ok is False
    assert "expired" in reason.lower()


def test_lockout_after_max_attempts():
    store, now = _store()
    code = store.issue()
    for _ in range(6):
        store.verify("999999")
    ok, reason = store.verify(code)
    assert ok is False
    assert "many attempts" in reason or "locked" in reason.lower()


def test_no_code_means_reject():
    store, now = _store()
    ok, _ = store.verify("123456")
    assert ok is False
