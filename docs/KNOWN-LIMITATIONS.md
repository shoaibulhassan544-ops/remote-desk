# Known Limitations & Security Notes — RemoteDesk v1.0.0

## Functional limitations
- **LAN only.** No internet relay in v1. Cross-network sessions need
  port-forward/VPN or a future relay deployment.
- **One session at a time** per host. A second guest is refused while one is active.
- **Primary monitor only.** No multi-monitor selection, no per-window capture.
- **Screen capture via `mss`**, not Windows Graphics Capture API (documented
  trade-off in docs/04). Cannot capture locked screens / UAC secure desktop.
- **Keyboard input: single characters only in v1.** Special keys (Ctrl/Alt/Win/
  arrows/function keys) are not forwarded yet.
- **File-transfer UI:** "Send a file…" shows the permission note; the actual
  file-picker send is not wired in the v1 UI (protocol implemented + tested at
  the module level).
- **No mid-session permission toggle UI** (revoke exists in session logic).
- **No audio, no chat, no multi-monitor, no mobile clients.**
- **No code signing:** Windows SmartScreen may warn on first install.
- **Update = manual download + install.** No silent auto-install (intentional).
- **No per-message replay nonce** in v1 (TLS provides transport-level protection).
- **Self-signed cert (TOFU):** first connection trusts the host cert; pairing
  auth still required, but verify pairing codes out-of-band.

## Security notes
- Pairing codes are 6 digits: safe only with TTL + single-use + lockout (all on).
- Unattended password strength is the owner's responsibility (min 10 chars enforced).
- The dev-only signaling stub must never be internet-exposed (no auth).
- Audit log never contains passwords, tokens, keys, or screen content — by code
  (no such fields exist in the log path).

## Compatibility
- Target: Windows 10 / 11 x64. Not tested on Windows 10/11 yet (needs Windows
  machines — see TEST-REPORT). Not supported on macOS/Linux as a packaged app
  (source runs on Linux for dev/loopback only).
