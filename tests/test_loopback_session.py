"""Bug B (v1.0.7) loopback proof: HostServer + RemoteClient in-process.

With an auto-accepting host (control=True), the client must:
1) connect,
2) receive >=1 screen frame within 5s (with REAL host w/h metadata),
3) have an input_event reach the host (via the on_input_event test hook —
   the test NEVER moves the real mouse).

Screen capture is monkeypatched to a tiny valid JPEG because CI/headless
machines have no display; the wire path (TLS + frames + input) is real.
"""

import io
import os
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

import app.screen as screen_mod  # noqa: E402
from app.client import RemoteClient  # noqa: E402
from app.host import HostServer  # noqa: E402


def _tiny_jpeg() -> bytes:
    img = Image.new("RGB", (320, 200), (10, 60, 160))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_loopback_frames_and_input_flow():
    port = _free_port()
    frames: list = []
    frame_meta: list = []
    inputs: list = []
    orig_capture = screen_mod.capture_jpeg_with_size

    def fake_capture(quality=70, max_width=1920):
        return _tiny_jpeg(), 320, 200

    screen_mod.capture_jpeg_with_size = fake_capture
    try:
        with tempfile.TemporaryDirectory() as tmp:
            host = HostServer(
                "111222333", "HostPC", port, {"fps": 10}, data_dir=tmp,
                on_request=lambda peer: (True, True, False),
                on_log=lambda m: None,
                on_input_event=inputs.append)
            host.start()
            try:
                client = RemoteClient(
                    "999888777", "GuestPC",
                    on_frame=lambda jpeg: frames.append(jpeg),
                    on_status=lambda m: None,
                    on_disconnect=lambda r: None)
                ok, msg = client.connect("127.0.0.1", port)
                assert ok, f"connect failed: {msg}"
                try:
                    deadline = time.time() + 5.0
                    while time.time() < deadline and not frames:
                        time.sleep(0.05)
                    assert frames, "no screen frame received within 5s"
                    assert client.host_screen_size == (320, 200), (
                        f"host screen size not received: {client.host_screen_size}")
                    # Input must reach the host (via the test hook).
                    sent = client.send_input({"kind": "move", "x": 160, "y": 100})
                    assert sent is True
                    deadline = time.time() + 5.0
                    while time.time() < deadline and not inputs:
                        time.sleep(0.05)
                    assert inputs, "input event never reached the host"
                    assert inputs[0].get("kind") == "move"
                    assert (inputs[0].get("x"), inputs[0].get("y")) == (160, 100)
                finally:
                    client.disconnect()
            finally:
                host.stop()
    finally:
        screen_mod.capture_jpeg_with_size = orig_capture


def test_view_only_session_does_not_forward_input():
    """If the host grants view-only (control=False), send_input is refused."""
    port = _free_port()
    inputs: list = []
    orig_capture = screen_mod.capture_jpeg_with_size

    def fake_capture(quality=70, max_width=1920):
        return _tiny_jpeg(), 320, 200

    screen_mod.capture_jpeg_with_size = fake_capture
    try:
        with tempfile.TemporaryDirectory() as tmp:
            host = HostServer(
                "111222333", "HostPC", port, {"fps": 10}, data_dir=tmp,
                on_request=lambda peer: (True, False, False),
                on_log=lambda m: None,
                on_input_event=inputs.append)
            host.start()
            try:
                client = RemoteClient("999888777", "GuestPC",
                                      on_frame=lambda j: None,
                                      on_status=lambda m: None,
                                      on_disconnect=lambda r: None)
                ok, _ = client.connect("127.0.0.1", port)
                assert ok
                try:
                    assert client.send_input({"kind": "move", "x": 1, "y": 1}) is False
                    time.sleep(0.3)
                    assert inputs == [], "view-only session forwarded input!"
                finally:
                    client.disconnect()
            finally:
                host.stop()
    finally:
        screen_mod.capture_jpeg_with_size = orig_capture
