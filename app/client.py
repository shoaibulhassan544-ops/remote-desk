"""Guest/client side: connect to a host, authenticate, receive frames.

The client never assumes it is connected: every send/receive is guarded,
errors surface as readable messages, and disconnect cleans up the socket.
"""

import socket
import ssl
import threading
import time

from . import config, protocol, security
from .session import Session, SessionManager


class RemoteClient:
    def __init__(self, device_id: str, device_name: str,
                 on_frame=None, on_status=None, on_disconnect=None):
        self.device_id = device_id
        self.device_name = device_name
        self.on_frame = on_frame or (lambda jpeg: None)
        self.on_status = on_status or (lambda msg: None)
        self.on_disconnect = on_disconnect or (lambda reason: None)
        self.sessions = SessionManager()
        self._conn = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.latency_ms: float | None = None
        # Host screen size in pixels, from the latest screen_frame
        # payload (w/h). (0, 0) = unknown yet — UI falls back to raw coords.
        self.host_screen_size: tuple[int, int] = (0, 0)

    @property
    def connected(self) -> bool:
        return self.sessions.active is not None

    def connect(self, host: str, port: int, pairing_code: str = "",
                unattended_password: str = "") -> tuple[bool, str]:
        """Connect + authenticate. Returns (ok, message). Blocking (<= ~15s).

        Assisted (default): sends method "request" — no code. The host
        shows the Accept/Reject popup and decides. Unattended: password
        only, no popup (opt-in, host-enabled).
        """
        if self.connected:
            return False, "Already connected. Disconnect first."
        try:
            raw = socket.create_connection((host, int(port)),
                                           timeout=config.CONNECT_TIMEOUT_S)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # identity via host Accept (assisted) or unattended password
            conn = ctx.wrap_socket(raw, server_hostname=host)
        except (OSError, ssl.SSLError, ValueError) as exc:
            return False, f"Could not connect to {host}:{port}: {exc}"
        self._conn = conn
        buf = bytearray()
        try:
            self._send("hello", {"device_id": self.device_id,
                                 "device_name": self.device_name})
            if unattended_password:
                auth = {"method": "unattended", "password": unattended_password}
            else:
                auth = {"method": "request", "device_id": self.device_id,
                        "device_name": self.device_name}
            self._send("auth", auth)
            reply = self._read_message(buf)
        except (OSError, ValueError) as exc:
            self._close()
            return False, f"Authentication failed: {exc}"
        if reply is None:
            self._close()
            return False, "Host did not respond to authentication."
        if reply.get("type") == "auth_failed":
            reason = reply.get("payload", {}).get("reason", "Authentication failed.")
            self._close()
            return False, reason
        if reply.get("type") != "auth_ok":
            self._close()
            return False, "Unexpected response from host."
        payload = reply.get("payload", {})
        session = Session(session_id=f"c-{int(time.time())}",
                          peer_device_id=str(payload.get("host_id", "")),
                          peer_device_name=str(payload.get("host_name", host)),
                          direction="outgoing")
        session.can_control = bool(payload.get("control"))
        session.can_file_transfer = bool(payload.get("file_transfer"))
        self.sessions.start(session)
        self._stop.clear()
        self._thread = threading.Thread(target=self._receive_loop, args=(buf,),
                                         daemon=True)
        self._thread.start()
        self.on_status(f"Connected to {session.peer_device_name}.")
        return True, "Connected."

    def disconnect(self):
        self._stop.set()
        try:
            if self._conn:
                self._send("disconnect", {"reason": "Guest disconnected."})
        except OSError:
            pass
        self.sessions.end_active("ended")
        self._close()
        self.on_disconnect("Disconnected.")

    def send_input(self, event: dict) -> bool:
        if not self.connected or not self.sessions.active.can_control:
            return False
        try:
            self._send("input_event", {"event": event})
            return True
        except OSError:
            return False

    def send_ping(self):
        try:
            t0 = time.time()
            self._send("ping", {})
            self.latency_ms = (time.time() - t0) * 1000
        except OSError:
            pass

    # ------------------------------------------------------------- internals
    def _receive_loop(self, buf: bytearray):
        assert self._conn is not None
        self._conn.settimeout(1.0)
        while not self._stop.is_set() and self.connected:
            try:
                data = self._conn.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            buf.extend(data)
            try:
                msgs = protocol.decode_frames(buf)
            except ValueError:
                break
            for msg in msgs:
                ok, _ = security.validate_message(msg)
                if not ok:
                    continue
                if msg["type"] == "screen_frame":
                    try:
                        w = int(msg["payload"].get("w") or 0)
                        h = int(msg["payload"].get("h") or 0)
                        if w > 0 and h > 0:
                            self.host_screen_size = (w, h)
                        self.on_frame(protocol.b64d(msg["payload"].get("jpeg_b64", "")))
                    except (ValueError, KeyError):
                        pass
                elif msg["type"] == "disconnect":
                    self._stop.set()
        if self.connected:
            self.sessions.end_active("ended")
            self.on_disconnect("Host ended the session.")
        self._close()

    def _send(self, mtype: str, payload: dict):
        assert self._conn is not None
        self._conn.sendall(protocol.encode_message(mtype, payload))

    def _read_message(self, buf: bytearray) -> dict | None:
        assert self._conn is not None
        self._conn.settimeout(config.CONNECT_TIMEOUT_S)
        deadline = time.time() + config.CONNECT_TIMEOUT_S
        while time.time() < deadline:
            try:
                data = self._conn.recv(65536)
            except socket.timeout:
                continue
            if not data:
                return None
            buf.extend(data)
            msgs = protocol.decode_frames(buf)
            if msgs:
                return msgs[0]
        return None

    def _close(self):
        try:
            if self._conn:
                self._conn.close()
        except OSError:
            pass
        self._conn = None
