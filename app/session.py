"""Session state, permissions, and audit logging.

Permissions model:
- view: always granted for an accepted session (host sees the banner).
- control: ONLY after the host ticks "Allow control" (assisted) or the
  guest authenticated with the unattended password AND the host enabled
  unattended control. Revocable at any time; input stops immediately.
- file_transfer: ONLY after explicit per-session acceptance.

Audit log records: timestamps, device IDs/names, outcomes, permission
changes. It NEVER records passwords, tokens, keys, or screen content.
"""

import time
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    peer_device_id: str
    peer_device_name: str
    direction: str  # "incoming" | "outgoing"
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    outcome: str = "active"  # active | ended | rejected | failed | expired
    can_view: bool = True
    can_control: bool = False
    can_file_transfer: bool = False
    transport: str = "lan-tls-direct"
    bytes_sent: int = 0
    bytes_received: int = 0

    def grant(self, what: str):
        if what == "control":
            self.can_control = True
        elif what == "file_transfer":
            self.can_file_transfer = True

    def revoke(self, what: str):
        if what == "control":
            self.can_control = False
        elif what == "file_transfer":
            self.can_file_transfer = False
        elif what == "all":
            self.can_control = False
            self.can_file_transfer = False

    def end(self, outcome: str = "ended"):
        self.outcome = outcome
        self.ended_at = time.time()
        self.revoke("all")


@dataclass
class AuditEntry:
    ts: float
    event: str
    device_id: str
    detail: str  # must never contain secrets or screen content


class SessionManager:
    def __init__(self):
        self.active: Session | None = None
        self.audit: list[AuditEntry] = []

    def log(self, event: str, device_id: str, detail: str):
        self.audit.append(AuditEntry(time.time(), event, device_id, detail))

    def start(self, session: Session):
        if self.active is not None:
            raise RuntimeError("A session is already active.")
        self.active = session
        self.log("session_started", session.peer_device_id,
                 f"{session.direction} session with {session.peer_device_name}")

    def end_active(self, outcome: str = "ended"):
        if self.active is not None:
            self.active.end(outcome)
            self.log("session_ended", self.active.peer_device_id,
                     f"outcome={outcome}")
            self.active = None

    def revoke_control(self):
        if self.active is not None:
            self.active.revoke("control")
            self.log("control_revoked", self.active.peer_device_id,
                     "Host revoked control permission")
