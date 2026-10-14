# Task Checklist, Roadmap, Assumptions & Risks — RemoteDesk

## Checklist
- [x] Inspect environment (Python 3.12 on Linux dev VM; pytest installed)
- [x] 7 planning docs (PRD → testing/release plan)
- [x] Stack decision documented (Python/tkinter/TLS — NOT Tauri, with reasons)
- [x] Update-without-server design (GitHub Releases; Drive = manual link only)
- [x] App modules: config/version/device_id/security/protocol/screen/input/
      clipboard/file_transfer/session/discovery/update_checker/storage/host/client/ui/main
- [x] Host: TLS listen, pairing auth, Accept/Reject dialog, banner, disconnect
- [x] Client: connect, auth, frame receive, input send, disconnect
- [x] Unattended: opt-in, hash-only password, disable/revoke
- [x] File transfer: permission-gated, traversal-safe, never auto-executes
- [x] Update popup + manual check
- [x] Signaling stub (dev-only) + TURN deployment guide
- [x] Build: requirements, build.bat, PyInstaller spec, Inno Setup script, Actions workflow
- [x] Tests (6 files, 33 tests) — all pass; py_compile passes
- [x] Loopback TLS host↔guest verified (connect + reject)
- [ ] 2-Windows-PC LAN test — BLOCKED (needs 2 Windows PCs)
- [ ] Windows EXE + installer via GitHub Actions — PENDING (needs repo + tag)
- [ ] Update popup vs real GitHub Release — PENDING (needs repo + Release)
- [ ] Drive upload + share link — PENDING (Drive not connected)
- [ ] Internet relay — DEFERRED (needs relay deployment + owner decision)

## Roadmap
| Milestone | Status |
|---|---|
| Phase 1 Foundation | Done |
| Phase 2 LAN MVP | Code done; live 2-PC test pending |
| Phase 3 Internet | Deferred — relay not deployed |
| Phase 4 Security/Management | Code done |
| Phase 5 Release | Pending Actions build + verification |

## Assumptions
- Owner has a GitHub account (for Releases-based updates + Actions builds).
- Users run Windows 10/11 x64; Python not required on user machines (packaged EXE).
- LAN use is the v1 target; same-Wi-Fi is NOT assumed to guarantee connectivity.
- Owner publishes updates by pushing a `v*` tag (see SETUP_UPDATE.md).

## Risks
- **No code signing:** Windows SmartScreen may warn on first install. Mitigation:
  document; future: buy a code-signing cert.
- **Self-signed cert TOFU:** LAN attacker could present a fake cert. Mitigation:
  pairing auth still required; out-of-band code sharing.
- **Broadcast discovery blocked:** some routers/APs isolate clients. Mitigation:
  manual IP entry always available.
- **Screen capture on locked/UAC screens:** `mss` cannot capture secure desktops.
- **Update check relies on GitHub availability** + correct `UPDATE_REPO` config.
