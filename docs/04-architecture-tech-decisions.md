# System Architecture & Technology Decisions — RemoteDesk v1.0.0

## 1. Module map (separation of concerns)
```
app/main.py          entry point (GUI / --version / --check-update)
app/config.py        constants, product name, ports, update URL
app/version.py       VERSION = "1.0.0"
app/device_id.py     stable device ID + name, persisted
app/security.py      pairing codes, PBKDF2, TLS certs, validation, rate limit
app/protocol.py      length-prefixed JSON framing, base64 helpers
app/screen.py        mss capture -> JPEG (guarded)
app/input_control.py pynput input (guarded, permission-checked by caller)
app/clipboard_sync.py pyperclip (guarded, opt-in)
app/file_transfer.py chunked transfer, traversal-safe destinations
app/session.py       session state, permissions, audit log (no secrets)
app/discovery.py     UDP broadcast LAN discovery (presence only)
app/update_checker.py GitHub Releases check + semver compare
app/storage.py       JSON settings / trusted / history (hash-only secrets)
app/host.py          TLS server, assisted consent, screen streaming
app/client.py        TLS client, auth, frame receive loop
app/ui.py            tkinter UI (all 8 tabs + 2 dialogs)
server/signaling_stub.py  DEV-ONLY stub, no auth, LAN testing only
```

## 2. STACK DECISION (explicit feasibility decision)

The original brief preferred **Tauri + Rust + WebRTC**. That stack was
**rejected for v1** after feasibility review:

| Concern | Tauri/Rust/WebRTC | Chosen: Python + tkinter + TLS sockets |
|---|---|---|
| Build from this Linux VM into a verified Windows EXE | Not verifiable here: Rust/WebRTC native toolchain + Tauri bundler are high-failure-risk without a Windows machine | PyInstaller + Inno Setup via GitHub Actions (windows-latest) — the same route already proven for the owner's other tools |
| Working LAN MVP in one pass | WebRTC native build + signaling complexity; high chance of UI-only prototype | stdlib `ssl` + sockets: real encrypted stream, verified by loopback test |
| Owner's maintenance | New toolchain for the owner | Python/tkinter matches his existing tools (same UI conventions) |
| Screen capture | Windows Graphics Capture API (WinRT) — complex bindings | `mss` (cross-platform, simple) — documented trade-off below |

**Decision: Python 3.11 + tkinter + stdlib TLS sockets + mss/Pillow + pynput
(guarded) + PyInstaller + Inno Setup + GitHub Actions.** If a Windows-only
dependency is missing, its import is guarded and the feature reports
"unavailable" — never a faked connection.

### Screen capture trade-off
- Chosen: `mss` — simple, works on Windows 10/11, no WinRT bindings.
- Not chosen: Windows Graphics Capture API — better (per-window capture, less
  overhead) but needs WinRT interop; kept as a documented future upgrade.
- v1 captures the primary monitor only.

### Video transport trade-off
- Chosen: TLS TCP + JPEG frames at ~10 fps. Simple, encrypted, firewall-friendly
  on LAN. Latency is acceptable for assistance use.
- Not chosen: WebRTC (lower latency, but native build risk) / raw UDP (no
  encryption, loss handling). Future: WebRTC data/video channel if a native
  build pipeline is proven.

## 3. Update-without-server design
- Owner has NO server. Update source = **GitHub Releases** (free).
- Client: `GET https://api.github.com/repos/<OWNER>/<REPO>/releases/latest`
  on startup (≤ once/day) + manual "Check for Updates".
- Compare `tag_name` semver vs running version → popup (changelog + Download
  opens release page in browser + Later).
- **Google Drive is NOT the update source**: Drive has no version API, so the
  app cannot detect a new Drive file. Drive is only a manual share-the-installer
  link. This is stated in README, BUILD_EXE.md, SETUP_UPDATE.md, and the UI.
- Config: UPDATE_REPO = "shoaibulhassan544-ops/remote-desk"; `UPDATE_CHECK_URL` derived.
- No auto-install in v1: the user downloads + runs the new installer (safer:
  no silent code execution from an updater). Future: signed MSI + in-app install.

## 4. TLS + pairing design
- Transport: TLS 1.2+ via stdlib `ssl`. Host presents a per-device self-signed
  cert (generated on first run, key file 0o600).
- Identity is NOT "trust this cert blindly": the guest proves authorization via
  the pairing code (assisted) or unattended password; the host human Accepts.
  (TOFU risk documented in the threat model.)
- Pairing code: 6 digits, 5-min TTL, single-use, 5 attempts → 5-min lockout.
- Unattended: salted PBKDF2-HMAC-SHA256 (210k iterations) hash only.
- Auth attempts rate-limited per peer IP (5 / 5 min window).
- Session TTL 8 h; disconnect revokes all permissions + closes sockets.

## 5. Networking
- LAN: direct TLS TCP on port 47900 (configurable) + UDP broadcast discovery
  on 47901 (presence only). One session at a time in v1.
- Internet: NOT in v1. Needs port-forward/VPN or a deployed relay. See
  docs/06-database-networking-api-spec.md §4 and docs/TURN-DEPLOYMENT.md.
- Never assume same-Wi-Fi = reachable: client isolation, firewalls, different
  subnets are handled with readable errors (see TROUBLESHOOTING.md).

## 6. Storage
- JSON files under `%APPDATA%/RemoteDesk`: settings, trusted devices, history.
- No database server. No reversible secrets stored (password = hash only).
- Audit log: timestamps, IDs, outcomes, permission changes — never secrets or
  screen content.
