"""Security primitives: pairing codes, password hashing, TLS certs,
message validation, path-traversal rejection, rate limiting.

Rules enforced here:
- No hardcoded secrets. No plaintext secret is ever transmitted.
- Passwords are stored as salted PBKDF2 hashes only (never reversible).
- Private keys are stored with restrictive file permissions (0o600).
- No passwords / tokens / keys / screen content are ever logged.
- No custom encryption: PBKDF2-HMAC-SHA256 + TLS via stdlib ssl.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass, field

from . import config

# ---------------------------------------------------------------- pairing code
def generate_pairing_code() -> str:
    """6-digit one-time pairing code (zero-padded)."""
    return f"{secrets.randbelow(10 ** config.PAIRING_CODE_LENGTH):06d}"


@dataclass
class PairingCodeStore:
    """One active pairing code with expiry + attempt rate limiting.

    The host generates a code and shows it to the person in front of the
    screen (or reads it over a trusted channel). The guest must present it
    within the TTL. After MAX attempts the code locks for LOCKOUT seconds.
    """
    code: str = ""
    expires_at: float = 0.0
    attempts: int = 0
    locked_until: float = 0.0
    _now: callable = field(default=time.time, repr=False)

    def issue(self) -> str:
        self.code = generate_pairing_code()
        self.expires_at = self._now() + config.PAIRING_CODE_TTL_S
        self.attempts = 0
        self.locked_until = 0.0
        return self.code

    def verify(self, candidate: str) -> tuple[bool, str]:
        now = self._now()
        if now < self.locked_until:
            return False, "Too many attempts. Try again later."
        if not self.code or now > self.expires_at:
            return False, "Pairing code expired. Ask the host for a new code."
        self.attempts += 1
        if self.attempts > config.PAIRING_MAX_ATTEMPTS:
            self.locked_until = now + config.PAIRING_LOCKOUT_S
            self.code = ""
            return False, "Too many attempts. Code locked for 5 minutes."
        if hmac.compare_digest(str(candidate).strip(), self.code):
            self.code = ""  # single use
            self.attempts = 0
            return True, "OK"
        return False, "Incorrect pairing code."

# ---------------------------------------------------------------- passwords
def hash_password(password: str, salt: bytes | None = None) -> str:
    """PBKDF2-HMAC-SHA256, 210k iterations. Returns 'salt_b64$hash_b64'."""
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, hash_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


def validate_unattended_password(password: str) -> tuple[bool, str]:
    if len(password) < config.UNATTENDED_MIN_PASSWORD_LEN:
        return False, f"Password must be at least {config.UNATTENDED_MIN_PASSWORD_LEN} characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        return False, "Password must contain at least one letter and one digit."
    return True, "OK"

# ---------------------------------------------------------------- TLS certs
def ensure_tls_cert(cert_dir: str) -> tuple[str, str]:
    """Return (cert_path, key_path). Generate a self-signed cert on first run.

    Requires the `cryptography` package. The cert is per-device and used
    only to encrypt the TLS channel; peer identity is established by the
    pairing code / unattended password + device ID, NOT by trusting this
    cert blindly (see docs/05-security-threat-model.md: TOFU + pairing).
    The private key file is created with 0o600 permissions.
    """
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "device_cert.pem")
    key_path = os.path.join(cert_dir, "device_key.pem")
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        import datetime
    except ImportError as exc:
        raise RuntimeError(
            "The 'cryptography' package is required to generate the TLS "
            "certificate. Install requirements.txt and retry."
        ) from exc
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RemoteDesk Device")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    # Private key first, with restrictive permissions.
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path

# ---------------------------------------------------------------- validation
_ALLOWED_MSG_TYPES = {
    "hello", "auth", "auth_ok", "auth_failed", "request_control",
    "permission_update", "screen_frame", "input_event", "clipboard",
    "file_offer", "file_accept", "file_chunk", "file_done", "file_error",
    "ping", "pong", "disconnect", "error",
}


def validate_message(msg: object) -> tuple[bool, str]:
    """Validate a decoded protocol message. Returns (ok, reason)."""
    if not isinstance(msg, dict):
        return False, "Message must be a JSON object."
    mtype = msg.get("type")
    if mtype not in _ALLOWED_MSG_TYPES:
        return False, f"Unknown message type: {mtype!r}."
    if "seq" in msg and not isinstance(msg["seq"], int):
        return False, "Field 'seq' must be an integer."
    if "ts" in msg and not isinstance(msg["ts"], (int, float)):
        return False, "Field 'ts' must be a number."
    return True, "OK"


def is_safe_relative_path(path: str) -> tuple[bool, str]:
    """Reject path traversal and absolute-path escapes for file transfers."""
    if not path or not isinstance(path, str):
        return False, "Empty file path."
    p = path.replace("\\", "/")
    if p.startswith("/") or (len(p) >= 2 and p[1] == ":"):
        return False, "Absolute paths are not allowed."
    parts = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        return False, "Path traversal ('..') is not allowed."
    if any(c in p for c in ("\x00",)):
        return False, "NUL byte in path."
    if p != path and ".." in path:
        return False, "Path traversal ('..') is not allowed."
    return True, "OK"


def safe_join(base_dir: str, rel_path: str) -> str:
    """Join rel_path onto base_dir; raise ValueError if it escapes base_dir."""
    ok, reason = is_safe_relative_path(rel_path)
    if not ok:
        raise ValueError(reason)
    joined = os.path.normpath(os.path.join(base_dir, rel_path))
    base = os.path.normpath(base_dir)
    if joined != base and not joined.startswith(base + os.sep):
        raise ValueError("Resolved path escapes the transfer directory.")
    return joined


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    """Simple per-key attempt limiter (e.g. per peer IP for auth)."""

    def __init__(self, max_attempts: int = 5, window_s: float = 300.0,
                 now: callable = time.time):
        self.max_attempts = max_attempts
        self.window_s = window_s
        self._now = now
        self._attempts: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = self._now()
        recent = [t for t in self._attempts.get(key, []) if now - t < self.window_s]
        self._attempts[key] = recent
        if len(recent) >= self.max_attempts:
            return False
        recent.append(now)
        return True
