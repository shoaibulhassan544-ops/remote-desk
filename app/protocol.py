"""Wire protocol: length-prefixed JSON frames over TLS TCP.

Frame layout: 4-byte big-endian unsigned length N, then N bytes of UTF-8 JSON.
Max frame size enforced on decode (config.FRAME_MAX_BYTES) to bound memory.

Message envelope: {"type": str, "seq": int, "ts": float, "payload": {...}}
Screen frames carry base64 JPEG bytes in payload["jpeg_b64"].
File chunks carry base64 bytes in payload["data_b64"].
"""

import base64
import json
import struct
import time

from . import config

HEADER = struct.Struct(">I")


def encode_message(msg_type: str, payload: dict | None = None, seq: int = 0) -> bytes:
    envelope = {
        "type": msg_type,
        "seq": int(seq),
        "ts": time.time(),
        "payload": payload or {},
    }
    body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
    if len(body) > config.FRAME_MAX_BYTES:
        raise ValueError(f"Frame too large: {len(body)} bytes")
    return HEADER.pack(len(body)) + body


def decode_frames(buffer: bytearray) -> list[dict]:
    """Pull complete frames out of `buffer` (in place). Returns messages."""
    out: list[dict] = []
    while True:
        if len(buffer) < HEADER.size:
            return out
        (n,) = HEADER.unpack_from(buffer, 0)
        if n > config.FRAME_MAX_BYTES:
            raise ValueError(f"Frame length {n} exceeds max {config.FRAME_MAX_BYTES}")
        if len(buffer) < HEADER.size + n:
            return out
        body = bytes(buffer[HEADER.size:HEADER.size + n])
        del buffer[:HEADER.size + n]
        out.append(json.loads(body.decode("utf-8")))


def b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)
