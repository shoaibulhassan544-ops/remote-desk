"""Session permission tests: control/file transfer must be explicitly
granted and must stop the moment they are revoked or the session ends."""

import pytest

from app.session import Session, SessionManager


def _session():
    return Session(session_id="s1", peer_device_id="123456789",
                   peer_device_name="Test-PC", direction="incoming")


def test_permissions_default_denied():
    s = _session()
    assert s.can_control is False
    assert s.can_file_transfer is False
    assert s.can_view is True  # view comes with an accepted session


def test_grant_and_revoke_control():
    s = _session()
    s.grant("control")
    assert s.can_control is True
    s.revoke("control")
    assert s.can_control is False


def test_end_revokes_everything():
    s = _session()
    s.grant("control")
    s.grant("file_transfer")
    s.end("ended")
    assert s.can_control is False
    assert s.can_file_transfer is False
    assert s.outcome == "ended"
    assert s.ended_at is not None


def test_manager_rejects_second_active_session():
    mgr = SessionManager()
    mgr.start(_session())
    with pytest.raises(RuntimeError):
        mgr.start(_session())


def test_manager_end_clears_active_and_logs():
    mgr = SessionManager()
    s = _session()
    mgr.start(s)
    mgr.end_active("ended")
    assert mgr.active is None
    assert any(e.event == "session_ended" for e in mgr.audit)


def test_audit_log_never_holds_secrets():
    mgr = SessionManager()
    mgr.log("auth_failed", "123", "Invalid password attempt")
    assert "password123" not in str(mgr.audit)
