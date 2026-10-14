# Testing & Release Plan — RemoteDesk v1.0.0

## 1. Test layers
| Layer | What | Tool |
|---|---|---|
| Unit | version compare, pairing, traversal, protocol, rate limit, permissions | pytest (`tests/`) |
| Integration | host↔guest TLS loopback: connect, Accept, reject, wrong code | manual script (see TEST-REPORT) |
| UI smoke | app starts, tabs render, dialogs open | manual on Windows |
| Two-PC LAN | real assisted session between 2 Windows PCs | manual (BLOCKED — needs 2 Windows PCs) |
| Installer | install / launch / uninstall / upgrade on clean Windows | manual (needs Actions build) |

## 2. Test cases (minimum — from the brief)
- [x] Pairing: correct / wrong / expired / lockout / single-use (pytest)
- [x] Rejected request → no session (loopback + unit logic)
- [x] Invalid credentials / revoked devices (unit + loopback)
- [x] Input permission revocation (unit: revoke → can_control False)
- [x] Path traversal: `../`, absolute, `C:\` (pytest)
- [x] Protocol: framing, partial frames, oversize, unknown types (pytest)
- [x] Rate limiting (pytest)
- [ ] Network interruption + recovery (not yet verified — needs 2-PC test)
- [ ] Large file transfer + failed transfer (protocol implemented; not live-verified)
- [ ] App restart + credential persistence (settings round-trip; needs Windows run)
- [ ] Installation + uninstallation (needs Actions-built installer)
- [ ] Resource cleanup after disconnect (loopback: sockets closed; needs Windows check)
- [ ] Windows 10 + 11 compatibility (needs Windows machines)
- [ ] Connections across separate internet networks (out of scope for v1 — no relay)

## 3. Release plan
1. **Phase 1 — Foundation (done):** docs, structure, shell + dashboard, tests.
2. **Phase 2 — LAN MVP (done in code):** pairing, TLS, capture, input, file transfer.
3. **Phase 3 — Internet:** deferred — needs relay deployment + owner decision.
4. **Phase 4 — Security/management (done in code):** assisted + unattended + history + revoke + clipboard + files.
5. **Phase 5 — Release (pending):** 2-PC LAN test → Actions build → installer test →
   Release publish → update-popup verification → Drive share link.

## 4. Release gate (all must be true)
- pytest passes; py_compile passes on all sources.
- No secrets in code/logs (grep).
- 2-PC LAN assisted session verified end-to-end.
- Installer installs/launches/uninstalls on clean Windows.
- Update popup verified against a real GitHub Release.
- KNOWN-LIMITATIONS.md reviewed; no feature claimed as verified that is not.
