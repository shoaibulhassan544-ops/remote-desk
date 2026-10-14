"""Protocol framing + message validation tests."""

import pytest

from app import protocol
from app.security import validate_message


def test_encode_decode_roundtrip():
    raw = protocol.encode_message("ping", {"x": 1}, seq=7)
    buf = bytearray(raw)
    msgs = protocol.decode_frames(buf)
    assert len(msgs) == 1
    assert msgs[0]["type"] == "ping"
    assert msgs[0]["payload"] == {"x": 1}
    assert msgs[0]["seq"] == 7
    assert buf == bytearray()


def test_partial_frame_waits():
    raw = protocol.encode_message("pong", {})
    buf = bytearray(raw[:3])
    assert protocol.decode_frames(buf) == []
    buf.extend(raw[3:])
    assert len(protocol.decode_frames(buf)) == 1


def test_two_frames_in_one_buffer():
    buf = bytearray(protocol.encode_message("ping", {}) + protocol.encode_message("pong", {}))
    assert len(protocol.decode_frames(buf)) == 2


def test_oversize_frame_rejected():
    buf = bytearray(b"\xff\xff\xff\xff" + b"x" * 10)
    with pytest.raises(ValueError):
        protocol.decode_frames(buf)


def test_validate_message_ok():
    assert validate_message({"type": "hello", "seq": 1})[0] is True


def test_validate_message_rejects_unknown_type():
    assert validate_message({"type": "take_over_the_pc"})[0] is False


def test_validate_message_rejects_non_dict():
    assert validate_message(["hello"])[0] is False


def test_validate_message_rejects_bad_seq():
    assert validate_message({"type": "ping", "seq": "one"})[0] is False


def test_b64_roundtrip():
    assert protocol.b64d(protocol.b64e(b"\x00\xffhello")) == b"\x00\xffhello"
