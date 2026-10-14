"""Chunked file transfer over the session TLS channel.

- Permission-gated: the receiving side must accept each file_offer first.
- Destination paths are validated (no traversal, no absolute escapes).
- Received files are NEVER executed — the app only writes bytes to disk.
- Progress callbacks report (bytes_sent, total_bytes).
"""

import hashlib
import os

from . import config
from .security import is_safe_relative_path, safe_join


def file_offer_meta(path: str) -> dict:
    """Build the metadata dict for a file_offer message."""
    size = os.path.getsize(path)
    if size > config.MAX_TRANSFER_FILE_BYTES:
        raise ValueError(f"File too large: {size} bytes (max {config.MAX_TRANSFER_FILE_BYTES})")
    return {
        "name": os.path.basename(path),
        "size": size,
        "sha256": sha256_file(path),
    }


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_file_chunks(path: str, chunk_size: int = config.TRANSFER_CHUNK_SIZE):
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                return
            yield chunk


class FileReceiver:
    """Writes incoming chunks to the validated destination file."""

    def __init__(self, dest_dir: str, rel_name: str, expected_size: int,
                 expected_sha256: str = ""):
        ok, reason = is_safe_relative_path(rel_name)
        if not ok:
            raise ValueError(reason)
        self.dest_path = safe_join(dest_dir, os.path.basename(rel_name))
        self.expected_size = int(expected_size)
        self.expected_sha256 = expected_sha256
        self.received = 0
        self._fh = open(self.dest_path, "wb")

    def write_chunk(self, data: bytes) -> int:
        self._fh.write(data)
        self.received += len(data)
        return self.received

    def finish(self) -> dict:
        self._fh.close()
        ok = self.received == self.expected_size
        sha_ok = True
        if self.expected_sha256:
            sha_ok = sha256_file(self.dest_path) == self.expected_sha256
        return {"path": self.dest_path, "size_ok": ok, "sha256_ok": sha_ok,
                "received": self.received}

    def abort(self):
        try:
            self._fh.close()
        except Exception:
            pass
        try:
            os.remove(self.dest_path)
        except OSError:
            pass
