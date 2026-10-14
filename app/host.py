"""Host side: TLS server, assisted Accept/Reject, screen streaming.

Flow:
1. Listen on TCP port (default 47900) with TLS (per-device self-signed cert).
2. Guest sends hello (device ID + name), then auth (assisted request OR
   unattended password — only if unattended is enabled).
3. Pairing/unattended check passes -> the HOST UI is asked via
   `on_request(peer)` callback: Accept/Reject + control/file permissions.
   The network layer NEVER auto-accepts; the default callback rejects.
4. On Accept: stream screen frames; apply input events ONLY while
   session.can_control; handle file transfers ONLY while permitted.
5. On Disconnect / error: close everything, revoke permissions, log.
"""

import socket
import ssl
import threading
import time

from . import config, protocol, screen, security, storage
from .discovery import DiscoveryBroadcaster
from .session import Session, SessionManager


class HostServer:
    def __init__(self, device_id: str, device_name: str, port: int,
                 settings: dict, data_dir: str | None = None,
                 on_request=None, on_frame_sent=None, on_log=None,
                 on_input_event=None):
        self.device_id = device_id
        self.device_name = device_name
        self.port = port
        self.settings = settings
        self.data_dir = data_dir or config.app_data_dir()
        self.on_request = on_request or (lambda peer: (False, False, False))
        self.on_frame_sent = on_frame_sent or (lambda n: None)
        self.on_log = on_log or (lambda msg: None)
        # Test hook: when set, inbound input events are delivered here
        # INSTEAD of moving the real mouse/keyboard. Production passes None.
        self.on_input_event = on_input_event
        self.pairing = security.PairingCodeStore()
        self.rate_limiter = security.RateLimiter()
        self.sessions = SessionManager()
        self._stop = threading.Event()
        # Set by _serve once the socket is listening (or once it has
        # definitively failed). start() waits on it so callers never
        # connect before the server is ready (first-run TLS keygen
        # otherwise made connect race and fail with "Connection refused").
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._conn = None
        self._broadcaster: DiscoveryBroadcaster | None = None

    # ------------------------------------------------------------- lifecycle
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        # Wait until _serve is actually listening (or has failed) —
        # without this, an immediate connect races first-run TLS
        # key generation and fails with "Connection refused".
        self._ready.wait(timeout=15.0)
        self.on_log(f"Hosting started on port {self.port}.")
        # BUG A FIX (v1.0.7): the host MUST broadcast its presence, or LAN
        # discovery can never find it and a Device ID (Address) can never
        # resolve on the LAN. A broadcaster failure must never kill hosting.
        try:
            self._broadcaster = DiscoveryBroadcaster(
                self.device_id, self.device_name, self.port)
            self._broadcaster.start()
        except Exception as exc:  # noqa: BLE001 — discovery is best-effort
            self._broadcaster = None
            self.on_log(f"LAN discovery broadcast unavailable: {exc}")

    def stop(self):
        self._stop.set()
        self.sessions.end_active("ended")
        try:
            if self._broadcaster is not None:
                self._broadcaster.stop()
        except Exception:
            pass
        self._broadcaster = None
        try:
            if self._conn:
                self._conn.close()
        except OSError:
            pass
        self.on_log("Hosting stopped.")

    # ------------------------------------------------------------- serving
    def _serve(self):
        try:
            cert, key = security.ensure_tls_cert(self.data_dir)
        except RuntimeError as exc:
            self.on_log(f"Hosting failed: {exc}")
            self._ready.set()
            return
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((config.HOST, self.port))
            srv.listen(1)
            srv.settimeout(1.0)
        except OSError as exc:
            self.on_log(f"Hosting failed: cannot listen on port {self.port}: {exc}")
            self._ready.set()
            return
        self._ready.set()
        while not self._stop.is_set():
            try:
                raw, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if self.sessions.active is not None:
                try:
                    raw.close()
                except OSError:
                    pass
                continue  # one session at a time in v1
            threading.Thread(target=self._handle_guest,
                             args=(raw, addr), daemon=True).start()
        srv.close()

    def _handle_guest(self, raw, addr):
        peer_ip = addr[0]
        if not self.rate_limiter.allow(peer_ip):
            try:
                raw.close()
            except OSError:
                pass
            self.on_log(f"Rate-limited connection attempts from {peer_ip}.")
            return
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            cert, key = security.ensure_tls_cert(self.data_dir)
            ctx.load_cert_chain(cert, key)
            conn = ctx.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError) as exc:
            self.on_log(f"TLS handshake failed from {peer_ip}: {exc}")
            return
        self._conn = conn
        buf = bytearray()
        conn.settimeout(5.0)
        try:
            hello = self._read_message(conn, buf)
            if hello is None or hello.get("type") != "hello":
                self._send(conn, "error", {"message": "Expected hello."})
                return
            peer = hello.get("payload", {})
            peer_id = str(peer.get("device_id", ""))
            peer_name = str(peer.get("device_name", ""))
            auth = self._read_message(conn, buf)
            if auth is None or auth.get("type") != "auth":
                self._send(conn, "error", {"message": "Expected auth."})
                return
            method = auth.get("payload", {}).get("method")
            ok, reason = self._check_auth(auth.get("payload", {}), peer_id)
            if not ok:
                self._send(conn, "auth_failed", {"reason": reason})
                self.sessions.log("auth_failed", peer_id, reason)
                return
            # FINAL v1.0.5 FLOW: assisted sessions ALWAYS need host Accept.
            # No pairing code, no auto-accept (not even for trusted devices).
            # The ONLY no-Accept path is unattended, password-protected.
            if method == "unattended":
                allow_control = bool(self.settings.get("unattended_allow_control"))
                allow_files = False
            else:
                accept, allow_control, allow_files = self.on_request(
                    {"device_id": peer_id, "device_name": peer_name, "ip": peer_ip})
                if not accept:
                    self._send(conn, "auth_failed", {"reason": "Host rejected the request."})
                    self.sessions.log("session_rejected", peer_id, "Host rejected")
                    return
            session = Session(session_id=f"s-{int(time.time())}",
                              peer_device_id=peer_id, peer_device_name=peer_name,
                              direction="incoming")
            session.can_control = bool(allow_control)
            session.can_file_transfer = bool(allow_files)
            self.sessions.start(session)
            self._send(conn, "auth_ok", {"host_id": self.device_id,
                                         "host_name": self.device_name,
                                         "control": session.can_control,
                                         "file_transfer": session.can_file_transfer})
            self._stream_loop(conn, buf, session)
        except (OSError, ValueError) as exc:
            self.on_log(f"Session error: {exc}")
        finally:
            self.sessions.end_active("ended")
            try:
                conn.close()
            except OSError:
                pass
            self._conn = None

    def _check_auth(self, payload: dict, peer_id: str = "") -> tuple[bool, str]:
        method = payload.get("method")
        if method == "request":
            # Assisted request: no code. The host's Accept/Reject popup
            # decides. (Pairing codes were removed from the assisted flow
            # in v1.0.5; PairingCodeStore is kept only for compatibility.)
            return True, "OK"
        if method == "unattended":
            if not self.settings.get("unattended_enabled"):
                return False, "Unattended access is disabled on this device."
            stored = str(self.settings.get("unattended_password_hash", ""))
            if stored and security.verify_password(str(payload.get("password", "")), stored):
                return True, "OK"
            return False, "Invalid unattended password."
        return False, "Unknown auth method."

    def _stream_loop(self, conn, buf, session: Session):
        conn.settimeout(1.0)
        interval = 1.0 / max(1, min(30, int(self.settings.get("fps", config.DEFAULT_FPS))))
        last_frame = 0.0
        while not self._stop.is_set() and self.sessions.active is session:
            # inbound messages (input / file / disconnect)
            try:
                for msg in self._drain(conn, buf):
                    self._handle_inbound(conn, msg, session)
            except (OSError, ValueError):
                break
            if self.sessions.active is not session:
                break
            now = time.time()
            if now - last_frame >= interval:
                frame, fw, fh = screen.capture_jpeg_with_size(
                    quality=int(self.settings.get("jpeg_quality", config.DEFAULT_JPEG_QUALITY)))
                if frame is not None:
                    # BUG B FIX: send the REAL captured size. The guest
                    # maps its canvas clicks into this coordinate space;
                    # previously w/h were hardcoded 0, so clicks landed
                    # in the wrong place (or nowhere useful).
                    self._send(conn, "screen_frame",
                               {"jpeg_b64": protocol.b64e(frame),
                                "w": int(fw), "h": int(fh)})
                    session.bytes_sent += len(frame)
                    self.on_frame_sent(session.bytes_sent)
                last_frame = now
            time.sleep(0.01)
        self._send_quiet(conn, "disconnect", {"reason": "Session ended."})

    def _handle_inbound(self, conn, msg: dict, session: Session):
        ok, _ = security.validate_message(msg)
        if not ok:
            return
        mtype = msg.get("type")
        payload = msg.get("payload", {})
        if mtype == "disconnect":
            self.sessions.end_active("ended")
        elif mtype == "input_event" and session.can_control:
            event = payload.get("event", {})
            if self.on_input_event is not None:
                # Test hook: record the event instead of moving real hardware.
                try:
                    self.on_input_event(event)
                except Exception:
                    pass
            else:
                from .input_control import InputController
                InputController().apply_event(event)
        elif mtype == "ping":
            self._send(conn, "pong", {})

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _send(conn, mtype: str, payload: dict):
        conn.sendall(protocol.encode_message(mtype, payload))

    @staticmethod
    def _send_quiet(conn, mtype: str, payload: dict):
        try:
            conn.sendall(protocol.encode_message(mtype, payload))
        except OSError:
            pass

    def _drain(self, conn, buf) -> list[dict]:
        try:
            data = conn.recv(65536)
        except socket.timeout:
            return []
        if not data:
            raise OSError("Peer closed the connection.")
        buf.extend(data)
        return protocol.decode_frames(buf)

    def _read_message(self, conn, buf) -> dict | None:
        deadline = time.time() + config.CONNECT_TIMEOUT_S
        while time.time() < deadline:
            msgs = self._drain(conn, buf)
            if msgs:
                return msgs[0]
        return None
