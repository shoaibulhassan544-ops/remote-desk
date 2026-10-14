"""RemoteDesk signaling server — the AnyDesk-style ID → IP directory.

What it does:
  POST /register   {device_id, device_name, port} -> stores the device,
                   with the IP the request came from (X-Forwarded-For
                   first entry when behind a proxy, else peer address).
  GET  /lookup?device_id=XXX -> {peer: {device_id, device_name, ip, port}}
                   or 404 {error} when unknown.
  POST /unregister {device_id} -> removes the device.
  GET  /health -> {ok: true, devices: N} for uptime checks.

What it does NOT do (by design):
  - NO relay: screen / input / file traffic never passes through here.
    Peers connect directly over their own TLS session.
  - NO passwords: the pairing code / unattended password is never sent
    here and never stored here.
  - NO authentication on the directory itself: anyone who knows the
    server URL can register a device or look one up. Run it on a
    private URL (see docs/SIGNALING_DEPLOY.md) and treat a leaked URL
    like a leaked phone book — it reveals IPs, not sessions.

Rate limit: at most 1 register per device_id per 10 seconds (429).
Persistence: in-memory registry + JSON file (SIGNALING_DATA_FILE env
or ./signaling_registry.json next to this file). Stale entries older
than 24h are pruned on lookup/register.

Run locally:  python server/signaling_server.py --port 47902
Run on a host: PORT=10000 python server/signaling_server.py --host 0.0.0.0
Stdlib only — no dependencies.
"""

import argparse
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEVICE_ID_RE = re.compile(r"^\d{9}$")
REGISTER_MIN_INTERVAL_S = 10.0
ENTRY_TTL_S = 24 * 3600


def _default_data_file() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "signaling_registry.json")


class Registry:
    """Thread-safe Device ID -> {device_name, ip, port, updated_at}."""

    def __init__(self, data_file: str | None = None):
        self.data_file = data_file or os.environ.get(
            "SIGNALING_DATA_FILE", _default_data_file())
        self._lock = threading.Lock()
        self._devices: dict[str, dict] = {}
        self._last_register: dict[str, float] = {}
        self._load()

    def _load(self):
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._devices = {k: v for k, v in data.items()
                                 if isinstance(v, dict)}
        except (OSError, ValueError):
            self._devices = {}

    def _save(self):
        try:
            tmp = self.data_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._devices, f, indent=2)
            os.replace(tmp, self.data_file)
        except OSError:
            pass  # in-memory registry keeps working; persistence is best-effort

    def _prune(self, now: float):
        stale = [k for k, v in self._devices.items()
                 if now - float(v.get("updated_at", 0)) > ENTRY_TTL_S]
        for k in stale:
            self._devices.pop(k, None)

    def register(self, device_id: str, device_name: str, port: int,
                 ip: str) -> tuple[dict | None, str | None, int]:
        """Returns (entry, error, http_status)."""
        now = time.time()
        if not DEVICE_ID_RE.match(device_id or ""):
            return None, "device_id must be 9 digits", 400
        try:
            port = int(port)
        except (TypeError, ValueError):
            return None, "port must be a number", 400
        if not 1 <= port <= 65535:
            return None, "port must be 1–65535", 400
        with self._lock:
            last = self._last_register.get(device_id, 0)
            if now - last < REGISTER_MIN_INTERVAL_S:
                return None, "Too many registrations — wait a few seconds.", 429
            self._last_register[device_id] = now
            self._prune(now)
            entry = {"device_id": device_id,
                     "device_name": str(device_name or "")[:100],
                     "ip": ip, "port": port, "updated_at": now}
            self._devices[device_id] = entry
            self._save()
            return entry, None, 200

    def lookup(self, device_id: str) -> tuple[dict | None, str | None, int]:
        now = time.time()
        with self._lock:
            self._prune(now)
            entry = self._devices.get(device_id or "")
            if entry is None:
                return None, "Device ID not found on this signaling server.", 404
            return dict(entry), None, 200

    def unregister(self, device_id: str) -> bool:
        with self._lock:
            removed = self._devices.pop(device_id or "", None) is not None
            if removed:
                self._save()
            return removed

    def count(self) -> int:
        with self._lock:
            return len(self._devices)


def make_handler(registry: Registry):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep stdout clean
            pass

        def _send(self, status: int, obj: dict):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

        def _read_json(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > 65536:
                return {}
            try:
                raw = self.rfile.read(length)
                obj = json.loads(raw.decode("utf-8"))
                return obj if isinstance(obj, dict) else {}
            except (ValueError, UnicodeDecodeError, OSError):
                return {}

        def _client_ip(self) -> str:
            forwarded = self.headers.get("X-Forwarded-For") or ""
            if forwarded:
                first = forwarded.split(",")[0].strip()
                if first:
                    return first
            return self.client_address[0]

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/health"):
                self._send(200, {"ok": True, "service": "remotedesk-signaling",
                                 "devices": registry.count()})
                return
            if self.path.startswith("/lookup"):
                from urllib.parse import parse_qs, urlparse
                query = parse_qs(urlparse(self.path).query)
                did = (query.get("device_id") or [""])[0]
                entry, error, status = registry.lookup(did)
                if error:
                    self._send(status, {"ok": False, "error": error})
                else:
                    self._send(200, {"ok": True, "peer": entry})
                return
            self._send(404, {"ok": False, "error": "Not found."})

        def do_POST(self):
            if self.path == "/register":
                body = self._read_json()
                entry, error, status = registry.register(
                    str(body.get("device_id", "")), str(body.get("device_name", "")),
                    body.get("port", 0), self._client_ip())
                if error:
                    self._send(status, {"ok": False, "error": error})
                else:
                    self._send(200, {"ok": True, "peer": entry})
                return
            if self.path == "/unregister":
                body = self._read_json()
                removed = registry.unregister(str(body.get("device_id", "")))
                self._send(200, {"ok": True, "removed": removed})
                return
            self._send(404, {"ok": False, "error": "Not found."})

    return Handler


def main():
    ap = argparse.ArgumentParser(description="RemoteDesk signaling server (ID -> IP directory)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "47902")))
    ap.add_argument("--data", default=None, help="Registry JSON file path")
    args = ap.parse_args()
    registry = Registry(args.data)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(registry))
    print(f"RemoteDesk signaling server on {args.host}:{args.port} "
          f"(registry: {registry.data_file})")
    print("Directory only — no relay, no passwords. See docs/SIGNALING_DEPLOY.md.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.")


if __name__ == "__main__":
    main()
