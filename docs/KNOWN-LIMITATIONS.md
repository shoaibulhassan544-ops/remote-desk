# Known Limitations & Security Notes — RemoteDesk v1.0.4

## Functional limitations
- **Internet mode is direct TCP only — no relay.** The v1.0.4
  signaling server is a directory only (ID → IP); it does NOT proxy
  sessions. Direct TCP works when UPnP succeeds or manual port
  forwarding is set (router → TCP 47900 → host's LAN IP). If both
  fail (strict / CGNAT router with no public IPv4), a relay server
  would be needed and is NOT included in this build.
- **Device-ID connect REQUIRES the signaling server.** A 9-digit
  Device ID alone cannot resolve to an address — the v1.0.3 UI
  wrongly implied it could. In v1.0.4 the IP field rejects a bare
  Device ID, and ID connect works only when both PCs use the same
  signaling-server URL (Settings → Network). The server is NOT
  hosted for you — deploy it per docs/SIGNALING_DEPLOY.md.
- **Signaling directory is unauthenticated.** Anyone who knows the
  server URL can register / look up IDs and learn IPs. Keep the URL
  private. It never sees passwords or screen content.
- **One session at a time** per host. A second guest is refused while one is active.
- **Primary monitor only.** No multi-monitor selection, no per-window capture.
- **Screen capture via `mss`**, not Windows Graphics Capture API (documented
  trade-off in docs/04). Cannot capture locked screens / UAC secure desktop.
- **Keyboard input: single characters only in v1.** Special keys (Ctrl/Alt/Win/
  arrows/function keys) are not forwarded yet.
- **File-transfer SEND is not wired in the UI** (v1.0.3 states this honestly
  in the File Transfer tab: chooser works, Send sends nothing). The chunked
  protocol + traversal checks exist at module level and are tested.
- **No two-factor authentication.** The Settings toggle is present but
  disabled and labeled "not implemented in this build".
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
