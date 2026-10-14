# RemoteDesk — README

**Authorized remote-assistance software for your own computers.**
Temporary product name (rebrandable). Developed by Shoaib Azeez.

> **No backdoor. No hidden access. No silent enrollment.**
> Every remote session needs an explicit **Accept** on the host side, and
> control / file-transfer permissions are granted separately. Unattended
> access is opt-in, password-protected, and revocable.

## What it does (v1.0.7 — 3 real bug fixes + fresh UI rebuild)

- **BUG A FIXED — Address (Device ID) now resolves on LAN.** The host
  never broadcast its presence before, so LAN scan found nothing and a
  Device ID could never resolve. `HostServer.start()` now starts a
  `DiscoveryBroadcaster` (LAN broadcast + loopback, presence-only),
  and `start()` waits until the server is actually listening, so an
  immediate connect no longer races TLS key generation ("Connection
  refused"). If broadcast fails, hosting still starts (logged).
- **BUG B FIXED — IP connect now gives REAL access.** (1) The Accept
  popup's Control checkbox now defaults ON (host can still untick it),
  so sessions are no longer silently view-only. (2) The host sends its
  real screen size (w/h) with every frame; the viewer scales canvas
  clicks → host coords, so clicks land on the right folder/button.
  (3) The viewer shows "Waiting for screen…" until the first frame
  and a visible "Control: ON/OFF" indicator. Proven by a loopback
  test: host + client in-process, ≥1 frame received AND an input
  event reaching the host.
- **BUG C FIXED — small update popup, never-empty changelog.** The
  popup is now ~520×420 with ONLY [Download Update] [Later] (buttons
  in a grid with weights — no clipped "Later"). "What's new" uses a
  built-in changelog map when the GitHub Release body is empty, so it
  is never blank. Download starts immediately in-thread with live
  progress; on success the button becomes [Run Installer].
- **FRESH UI REBUILD** — `app/ui.py` deleted and rewritten from
  scratch in the same Option 1 AnyDesk Blue tokens (no leftover
  v1.0.4/v1.0.5 layout code).
- **Installer (v1.0.7):** `setup.iss` now ships `assets\icon.ico` into
  `{app}` AND both shortcuts (Start Menu + desktop) use
  `IconFilename="{app}\icon.ico"` directly — the desktop icon shows
  our logo even if EXE embedding ever fails. Install-while-running is
  now fully automatic: a `[Code]` `CurStepChanged` hook silently
  force-closes `RemoteDesk.exe` (`taskkill /F`, errors ignored)
  before files are replaced, on top of the v1.0.6 Restart Manager
  lines. CI now FAILS the build if the EXE has no icon resources
  (pefile check for RT_GROUP_ICON / RT_ICON). `icon.ico` rebuilt
  with all sizes: 16, 24, 32, 48, 64, 128, 256.
- Ship only v1.0.7+.

## What it does (v1.0.6 — v1.0.5 flow + installer auto-close fix)

- **FINAL FLOW — Address → Connect → Host Accept. No pairing code.**
  Home has ONE "Remote Address" box (Device ID ya IP) + big Connect
  button (+ Disconnect, Find on LAN; Enter also connects). The app
  auto-resolves: IP direct, Device ID via LAN scan, Device ID via
  signaling server (if configured). The host ALWAYS sees the Incoming
  Request popup (requester name + Device ID + IP, View/Control/File
  checkboxes, Accept green / Decline red, 60 s auto-reject). Host
  Accepts → session starts. Decline/timeout → controller sees
  "Host ne request decline kar di / jawab nahi diya."
- **Trusted Devices = address book ONLY.** One click fills the Remote
  Address field. It does NOT auto-accept — host Accept is still
  required every time.
- **Unattended = the ONLY no-Accept path.** Opt-in, password-protected:
  host enables it in Trusted Devices + sets a password; guest ticks
  "Unattended (password se)" and enters the password. No popup.
- **Option 1 "AnyDesk Blue" UI** (user-selected): deep navy `#0B1220`,
  card `#13203A`, bright-blue `#2E7DFF` primary/active nav, Home =
  YOUR ADDRESS + HOST THIS PC + CONNECT + Recent Sessions + Quick
  Actions + Activity log. Advanced options (connection type, signaling
  URL, Public IP/UPnP) live in Settings → Network only.
- **Centered update popup:** opens centered inside the app (never in a
  browser), fixed footer below the changelog with version row, progress
  bar + live status (`Downloading… 4.2 / 21.3 MB (20%) • 1.1 MB/s`),
  [Download Update] → [Run Installer] (click-only) + [Later].
- **Icon fix:** multi-size `.ico` (16–256) + desktop icon ON by default
  + embedded PNG fallback, so taskbar/desktop show the real logo.
  If Windows still shows the old icon: uninstall old version first +
  clear the icon cache (see docs/TROUBLESHOOTING.md).
- Pairing codes were REMOVED from the assisted flow in v1.0.5
  (PairingCodeStore kept only for compatibility). Ship only v1.0.7+.
- v1.0.6 installer fix: the installer now auto-closes a running
  RemoteDesk (Restart Manager) before replacing files. Before v1.0.6,
  upgrading while the app was running failed with "DeleteFile failed;
  code 5. Access is denied." — and the old UI stayed because the new
  EXE never replaced the old one.

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
  (Address + Connect), Recent Sessions from real history,
  Quick Actions, activity log, "Developed by Shoaib Azeez" footer
- Remote Control: Quick Connect / Saved Devices tabs, prominent blue
  Connect, actionable errors (e.g. "Host not reachable at X:47900 —
  check hosting ON, same Wi-Fi for LAN, or Public IP + port mapping
  for Internet"), Port, Unattended (password se) checkbox, Disconnect,
  Scan LAN
- **Internet (direct) mode, no relay server:** host shows Public IP +
  LAN IP + UPnP status + "Open port (UPnP)" + copyable "Public IP +
  Port + Address" line + port-forward guide. The controller
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
4. On the host PC: **Start Hosting**.
5. On the guest PC: enter the host's Address (Device ID ya IP) →
   **Connect**. The host must click **Accept** on the popup.
   (Unattended, password-protected, is the only no-Accept path.)

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
- Assisted sessions: host Accept popup is ALWAYS required — no pairing
  code, no auto-accept (not even for trusted devices). Trusted Devices
  is an address book only. Unattended (password, opt-in) is the only
  no-Accept path.
- Unattended password: salted PBKDF2 hash only, min 10 chars.
- No passwords / tokens / keys / screen content are ever logged.
- See docs/05-security-threat-model.md for the full model.
