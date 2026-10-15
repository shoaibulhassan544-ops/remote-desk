"""Connection Test — step-by-step diagnostics (v1.0.11).

The old flow gave the user one dead-end message ("Device ID nahi mila"
or a bare exception). The Connection Test runs 4 small steps and reports
each as PASS / FAIL in plain words, so the user can SEE exactly where
the connection breaks:

1. Address resolve — Device ID → LAN scan (or direct IP/hostname).
2. TCP connect — plain socket to host:port (proves reachability +
   that the host port is listening / not firewall-blocked).
3. TLS handshake — TLS wrap on the same socket (proves the host's
   TLS server is really answering).
4. Host jawab — INFO only: this test never sends auth, so no Accept
   popup appears. If steps 1–3 PASS, Connect dabao — host pe Accept
   popup aayega.

Every step has its own timeout and the runner never raises; a step
that times out is FAIL, not a crash. Network functions are injectable
so tests can mock them.
"""

import socket
import ssl

from . import connect_target, signaling
from .discovery import DiscoveryListener

STEP_TIMEOUT_S = 5.0


def _fail(detail: str) -> dict:
    return {"step": "", "status": "FAIL", "detail": detail}


def _resolve_step(address: str, settings: dict, scan_fn=None,
                  lookup_fn=None) -> tuple[dict, str | None, int]:
    """Step 1: resolve the typed address. Returns (result, host, port)."""
    port = int((settings or {}).get("port", 47900) or 47900)
    kind = connect_target.classify_address(address or "")
    if kind == "invalid":
        return (_fail("Address sahi nahi hai — Device ID (misal 739 738 074) "
                      "ya IP address (misal 192.168.1.100) likho."), None, port)
    if kind == "direct":
        host, explicit = connect_target.split_host_port(address)
        return ({"step": "Address resolve", "status": "PASS",
                 "detail": f"Direct IP/hostname: {host}"},
                host, explicit or port)
    # Device ID → LAN scan first, then signaling if configured.
    did = connect_target.digits_only(address)
    scan = scan_fn or (lambda: DiscoveryListener(duration_s=3.0).scan())
    try:
        found = scan() or {}
    except Exception:
        found = {}
    info = found.get(did) or {}
    if info.get("address"):
        return ({"step": "Address resolve", "status": "PASS",
                 "detail": f"Device ID LAN pe mila: {info['address']}"},
                info["address"], port)
    url = ((settings or {}).get("signaling_url") or "").strip()
    if url:
        lookup = lookup_fn or signaling.lookup_device
        try:
            peer, error = lookup(url, did)
        except Exception:
            peer, error = None, "Signaling server se jawab nahi mila."
        if peer and peer.get("ip"):
            return ({"step": "Address resolve", "status": "PASS",
                     "detail": f"Device ID signaling server se mila: {peer['ip']}"},
                    peer["ip"], int(peer.get("port") or port))
        return (_fail(f"Device ID LAN pe nahi mila, signaling se bhi nahi: {error}"),
                None, port)
    return (_fail("Device ID LAN pe nahi mila — Checklist: 1) Dusre PC pe "
                  "Start Hosting ON hai? 2) Dono PC ek hi Wi-Fi pe hain? "
                  "3) Firewall me RemoteDesk Allow hai?"), None, port)


def _tcp_step(host: str, port: int, tcp_connect_fn=None) -> tuple[dict, object | None]:
    """Step 2: plain TCP connect. Returns (result, raw_socket_or_None)."""
    connect = tcp_connect_fn or (lambda h, p, timeout: socket.create_connection(
        (h, p), timeout=timeout))
    try:
        raw = connect(host, port, STEP_TIMEOUT_S)
    except ConnectionRefusedError:
        return (_fail("Host ne connection mana kiya — dusre PC pe Start Hosting "
                      "ON karo + Firewall me RemoteDesk Allow karo."), None)
    except (TimeoutError, socket.timeout):
        return (_fail("Host tak pahuncha nahi (timeout) — IP sahi hai? Dono PC "
                      "ek hi Wi-Fi pe hain? Firewall me Allow hai?"), None)
    except OSError as exc:
        return (_fail(f"TCP connect fail: {exc}"), None)
    return ({"step": "TCP connect", "status": "PASS",
             "detail": f"{host}:{port} tak TCP connection ho gaya"}, raw)


def _tls_step(raw, host: str, tls_wrap_fn=None) -> dict:
    """Step 3: TLS handshake on the already-connected socket."""
    wrap = tls_wrap_fn or _default_tls_wrap
    try:
        conn = wrap(raw, host)
    except ssl.SSLError:
        return _fail("Security handshake fail — dono PC pe same version hai? "
                     "Dono pe latest RemoteDesk install karo.")
    except (OSError, ValueError) as exc:
        return _fail(f"TLS handshake fail: {exc}")
    try:
        conn.close()
    except OSError:
        pass
    return {"step": "TLS handshake", "status": "PASS",
            "detail": "Host ka TLS server jawab de raha hai"}


def _default_tls_wrap(raw, host: str):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx.wrap_socket(raw, server_hostname=host)


def run_connection_test(address: str, settings: dict | None = None,
                        scan_fn=None, lookup_fn=None,
                        tcp_connect_fn=None, tls_wrap_fn=None) -> list[dict]:
    """Run all 4 steps. Returns a list of step dicts. Never raises."""
    settings = settings or {}
    results: list[dict] = []
    try:
        step1, host, port = _resolve_step(address, settings, scan_fn, lookup_fn)
        step1["step"] = "1. Address resolve"
        results.append(step1)
        if step1["status"] != "PASS" or not host:
            return results
        step2, raw = _tcp_step(host, port, tcp_connect_fn)
        step2["step"] = "2. TCP connect"
        results.append(step2)
        if step2["status"] != "PASS" or raw is None:
            return results
        step3 = _tls_step(raw, host, tls_wrap_fn)
        step3["step"] = "3. TLS handshake"
        results.append(step3)
        try:
            raw.close()
        except OSError:
            pass
        if step3["status"] != "PASS":
            return results
        results.append({
            "step": "4. Host jawab",
            "status": "INFO",
            "detail": ("Teeno steps PASS hain — ab Connect dabao, host pe "
                       "Accept ka popup aayega. (Is test me actual connect "
                       "nahi kiya jata, is liye popup nahi aaya.)"),
        })
        return results
    except Exception as exc:  # noqa: BLE001 — diagnostics must never crash
        results.append({"step": "Connection Test", "status": "FAIL",
                        "detail": f"Test chalate waqt error: {exc}"})
        return results
