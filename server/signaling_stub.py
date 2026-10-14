"""DEV-ONLY signaling stub — NOT a production relay.

Purpose: lets two developers test the *signaling handshake concept*
(connection-intent exchange) on a LAN without a real server. It performs
NO authentication, NO encryption, and NEVER proxies screen data.
Screen/input/file traffic always flows directly between the two peers
over their own TLS session (see app/host.py + app/client.py).

For real Device-ID lookup, use the real server in
server/signaling_server.py (HTTP JSON API, see docs/SIGNALING_DEPLOY.md) —
this stub must NOT be used for that. If you expose this stub to the
internet, anyone could enumerate registered devices.

Run:  python server/signaling_stub.py --port 47902
"""

import argparse
import json
import socketserver
import threading
import time

REGISTRY: dict[str, dict] = {}
LOCK = threading.Lock()


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            raw = self.request.recv(4096)
            msg = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            return
        action = msg.get("action")
        with LOCK:
            if action == "register":
                REGISTRY[str(msg.get("device_id", ""))] = {
                    "device_name": msg.get("device_name", ""),
                    "address": self.client_address[0],
                    "port": msg.get("port", 47900),
                    "ts": time.time(),
                }
                reply = {"ok": True, "note": "DEV STUB ONLY — no auth performed."}
            elif action == "lookup":
                reply = {"ok": True, "peer": REGISTRY.get(str(msg.get("device_id", "")))}
            else:
                reply = {"ok": False, "error": "Unknown action."}
        try:
            self.request.sendall(json.dumps(reply).encode("utf-8"))
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=47902)
    args = ap.parse_args()
    print("WARNING: dev-only signaling stub. No auth, no encryption. LAN testing only.")
    with socketserver.ThreadingTCPServer(("0.0.0.0", args.port), Handler) as srv:
        srv.serve_forever()


if __name__ == "__main__":
    main()
