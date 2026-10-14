# RemoteDesk — README

**Authorized remote-assistance software for your own computers.**
Temporary product name (rebrandable). Developed by Shoaib Azeez.

> **No backdoor. No hidden access. No silent enrollment.**
> Every remote session needs an explicit **Accept** on the host side, and
> control / file-transfer permissions are granted separately. Unattended
> access is opt-in, password-protected, and revocable.

## What it does (v1.0.4 — Device-ID bug fix + signaling server + branding)

- **BUG FIX — a Device ID alone never connected (the screenshot bug).**
  The old Connect box said "Device ID or IP", but a 9-digit ID cannot
  resolve without a directory, so typing one only produced
  "not found on this LAN". In v1.0.4 the IP and Device ID are **separate
  fields**: the IP field **rejects** a bare 9-digit ID with a clear
  error, and a Device ID connects **only** via Signaling Server mode
  (or a LAN scan). A **Find on LAN** button scans and fills the IP in.
- **Signaling server (AnyDesk-style ID connect).** New
  `server/signaling_server.py` (stdlib only): `POST /register`,
  `GET /lookup`, `POST /unregister`, `GET /health`. It is a **directory
  only** — no relay, no passwords, no screen traffic. Deploy free on
  Render (`render.yaml` included) or any VPS — see
  [docs/SIGNALING_DEPLOY.md](docs/SIGNALING_DEPLOY.md). Settings →
  Network → Signaling server: paste the URL on both PCs; connection
  type → "Internet (via Signaling Server)". Without a server,
  Device IDs cannot resolve — use Direct IP.
- **Connection-type dropdown** (was radios — the 3rd option clipped
  off-screen in the screenshot): LAN / Internet direct / Internet via
  Signaling Server. Full-width, never clipped. Connection progress
  states: Resolving… → Connecting… → Waiting for host… → Connected.
- **Branding:** real logo (`assets/icon.png` / `icon.ico` — deep-blue
  rounded square + white monitor + blue double-arrow) wired to the
  window + taskbar icon, the EXE icon, the installer icon, and the
  Inno Setup wizard images (`installer_banner.bmp`,
  `installer_small.bmp`). "Developed by Shoaib Azeez" unchanged.

## What it does (v1.0.3 — blue reference UI + Internet direct mode)

- Blue reference UI (1000×680): sidebar Home / Remote Control / Viewer /
  File Transfer / Trusted Devices / Session History / Settings; deep navy
  `#0B1220` background, card `#13203A`, bright-blue `#2E7DFF` primary
  buttons + active nav (no gold), instant dark/light theme toggle
- Home: "Welcome Back!", Your Device ID card (formatted, Copy button),
  real OS label, host card (Start Hosting + pairing code), Connect box
  (Device ID / IP + pairing code), Recent Sessions from real history,
  Quick Actions, activity log, "Developed by Shoaib Azeez" footer
- Remote Control: Quick Connect / Saved Devices tabs, connection-type
  radios (LAN / Internet), prominent blue Connect, actionable errors
  (e.g. "Host not reachable at X:47900 — check hosting ON, same Wi-Fi
  for LAN, or Public IP + port mapping for Internet"), Port, pairing
  code, unattended checkbox, Disconnect, Scan LAN
- **Internet (direct) mode, no relay server:** host shows Public IP +
  LAN IP + UPnP status + "Open port (UPnP)" + copyable "Public IP +
  Port + Pairing code" line + port-forward guide. The controller
  connects with the same direct TCP/TLS path to the public IP. Works
  when UPnP succeeds or port forwarding is set; strict / CGNAT routers
  need a relay server, which is NOT included — the app says so instead
  of claiming otherwise.
- Incoming request dialog: requesting device name + ID + IP, View
  Screen / Control / File Transfer checkboxes, Accept (green) /
  Decline (red), **auto-reject after 60 s** with a log line
- Viewer toolbar: Connected status, quality from real measured frame
  size + fps (else "—"), latency "—" (no round-trip measurement in the
  protocol — never a fake ms number), Full-screen, red Disconnect
- File Transfer: Send / Receive tabs; chooser works, destination
  selector from trusted + history; **Send is NOT wired in this build —
  the Send button says so plainly and sends nothing**; Receive lists
  the real download folder ("never auto-executed")
- Trusted Devices: Add (ID + name) / Rename / Remove (revoke) +
  Unattended Access section (enable toggle + password, hash-only)
- Session History: real table (Device, Type, Duration, Status,
  Date & Time) with search-by-name + All / Remote Control / File
  Transfer filter
- Settings: Security / Network / General / About tabs — Change Access
  Password (hash-only), **2FA toggle DISABLED with "not implemented in
  this build"** (no fake 2FA), clipboard + file-transfer toggles,
  connection-type default, port, UPnP status, Public IP, port-reachable
  self-test, diagnostics (incl. Internet checks), download folder,
  theme toggle, auto-update toggle, About + Check for Updates
- In-app update download (unchanged from v1.0.2): popup downloads the
  installer inside the app with progress bar; Run Installer only on
  user click; browser fallback only when no installer asset exists or
  the download fails. See [docs/SETUP_UPDATE.md](docs/SETUP_UPDATE.md).

## What it does NOT do in v1.0.4

- **No internet relay.** The signaling server is a directory only —
  it hands out IPs, it does not proxy sessions. If direct TCP cannot
  reach the host (strict / CGNAT router, no UPnP, no port forwarding),
  a relay server would be needed and is NOT included. The included
  `server/signaling_stub.py` is a dev-only stub, not a relay.
- **Signaling server is NOT hosted for you.** You deploy it yourself
  (Render free tier / VPS) and paste the URL into both PCs. Until you
  do, Device-ID connect is unavailable and Direct IP is the way.
- **No file send over a live session yet** (chooser + queue UI exist;
  Send reports "not wired" honestly). The chunked protocol + traversal
  checks exist at module level.
- **No two-factor authentication** (toggle present but disabled, labeled).
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
| docs/SIGNALING_DEPLOY.md | Deploy the signaling server (Render / VPS) + curl tests |
| docs/TROUBLESHOOTING.md | Fixes for common failures |
| docs/RELEASE-CHECKLIST.md | Release gate |
| docs/KNOWN-LIMITATIONS.md | Limitations + security notes |

## Security summary

- TLS (stdlib `ssl`) for all session traffic; per-device self-signed cert.
- Pairing code: 6 digits, 5-minute expiry, single use, 5-attempt lockout.
- Unattended password: salted PBKDF2 hash only, min 10 chars.
- No passwords / tokens / keys / screen content are ever logged.
- See docs/05-security-threat-model.md for the full model.
