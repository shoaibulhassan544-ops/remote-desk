# RemoteDesk — README

**Authorized remote-assistance software for your own computers.**
Temporary product name (rebrandable). Developed by Shoaib Azeez.

> **No backdoor. No hidden access. No silent enrollment.**
> Every remote session needs an explicit **Accept** on the host side, and
> control / file-transfer permissions are granted separately. Unattended
> access is opt-in, password-protected, and revocable.

## What it does (v1.0.2 — LAN MVP + VIP UI + in-app updates)

- VIP sidebar UI (1000×680): Dashboard, Viewer, File Transfer, Trusted Devices,
  History, Security, Diagnostics, Settings & About + header status pill
  (Idle / Hosting ON / Connected) + instant dark/light theme toggle
- Dashboard "How to connect — 4 steps" card: host → Start Hosting + pairing code,
  note host IP + code, controller enters IP + port 47900 + code → Connect,
  host clicks Accept. No username needed. Both PCs on the same Wi-Fi.
- Assisted access: incoming request dialog (Accept/Reject + permission checkboxes)
- Real screen streaming over TLS (mss + JPEG), viewer with mouse/keyboard input
- Permission-gated file transfer (no traversal, never auto-executes)
- Optional clipboard sync (off by default)
- Trusted devices, session history, security settings, network diagnostics
- **In-app update download with NO server**: the app checks GitHub Releases
  for a newer version and shows a popup with changelog + progress bar;
  [Download Update] downloads the installer inside the app to
  `~/Downloads/RemoteDesk-Updates/`, then [Run Installer] (user-clicked only,
  never auto-executed). Browser redirect is only a fallback when no installer
  asset exists or the download fails.
  See [docs/SETUP_UPDATE.md](docs/SETUP_UPDATE.md).

## What it does NOT do in v1.0.2

- **No internet relay.** Internet mode needs port-forward/VPN or a deployed
  STUN/TURN relay (see [docs/TURN-DEPLOYMENT.md](docs/TURN-DEPLOYMENT.md)).
  The included `server/signaling_stub.py` is a dev-only stub, not a relay.
- No two-Windows-PC live test yet (see docs/TEST-REPORT.md — blocked item).

## Quick start (Windows)

1. Install Python 3.11.
2. `pip install -r requirements.txt`
3. `python -m app.main`
4. On the host PC: **Start Hosting**, share the 6-digit pairing code.
5. On the guest PC: enter host IP + pairing code → **Connect**.
   The host must click **Accept**.

## Build the installer

See [BUILD_EXE.md](BUILD_EXE.md) — push a `v*` tag to GitHub and Actions
builds `Setup-RemoteDesk-<version>.exe` + `RemoteDesk.exe`, and publishes a
GitHub Release (which is what triggers clients' update popup).

## Docs

| Doc | Contents |
|---|---|
| docs/01-PRD.md | Product requirements |
| docs/02-functional-requirements-user-stories.md | Features + user stories |
| docs/03-ui-ux-screen-flow.md | Screens + flows |
| docs/04-architecture-tech-decisions.md | Stack decision, update-without-server, TLS/pairing |
| docs/05-security-threat-model.md | Threat model |
| docs/06-database-networking-api-spec.md | Protocol, ports, discovery, update API |
| docs/07-testing-release-plan.md | Testing + release plan |
| docs/CHECKLIST.md | Task checklist, roadmap, assumptions, risks |
| docs/TEST-REPORT.md | Honest test status |
| docs/SETUP_UPDATE.md | Publish an update so clients get the popup (no server) |
| docs/TURN-DEPLOYMENT.md | coturn STUN/TURN deployment (no real secrets) |
| docs/TROUBLESHOOTING.md | Fixes for common failures |
| docs/RELEASE-CHECKLIST.md | Release gate |
| docs/KNOWN-LIMITATIONS.md | Limitations + security notes |

## Security summary

- TLS (stdlib `ssl`) for all session traffic; per-device self-signed cert.
- Pairing code: 6 digits, 5-minute expiry, single use, 5-attempt lockout.
- Unattended password: salted PBKDF2 hash only, min 10 chars.
- No passwords / tokens / keys / screen content are ever logged.
- See docs/05-security-threat-model.md for the full model.
