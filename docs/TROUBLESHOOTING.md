# Troubleshooting — RemoteDesk v1.0.0

## "Could not connect to <host>:<port>"
- Is the host PC's app open with **Hosting ON**? (Dashboard → Start Hosting)
- Same network? Both PCs on the same Wi-Fi/LAN, no VPN in between (v1 = LAN).
- Windows Firewall: allow `RemoteDesk.exe` (or TCP port 47900) on the host.
  First launch usually prompts; if you clicked Deny, re-allow in
  Windows Defender Firewall → Allow an app.
- Wrong IP? On the host: `ipconfig` → IPv4 address (e.g. 192.168.1.50).
- Client isolation: some guest Wi-Fi / hotspots block PC-to-PC traffic.
  Use a home router, or connect both PCs by cable / same router.

## "Host rejected the request" / "Host ne request decline kar di"
- The host clicked Decline (or ignored the dialog for 60 s = auto-reject).
  Ask them to Accept and tick the permission checkboxes you need.
- v1.0.5 has NO pairing codes in the assisted flow — a Decline is just
  a Decline; reconnecting sends a fresh request for the host to Accept.

## "Unattended access is disabled" / "Invalid unattended password"
- On the host: Trusted Devices page → enable unattended access + set a
  password (min 10 chars, letter + digit) → Save. Guest: tick
  "Unattended (password se)" and enter that exact password.

## Black / frozen viewer
- Host screen capture may be unavailable (locked screen, secure desktop).
  Unlock the host and reconnect.
- Diagnostics tab → Run diagnostics: check "Screen capture available".

## "Device ID not found" / typed a Device ID and it won't connect
- Since v1.0.5, Home has ONE "Remote Address" box: type the Device ID
  **or** the IP — the app auto-resolves it (LAN scan first, then the
  signaling server if one is configured). No separate IP field anymore.
- If the ID is not found: check hosting is ON on the other PC and both
  PCs are on the same Wi-Fi, or type that PC's IP address directly,
  or set up the signaling server (docs/SIGNALING_DEPLOY.md) and paste
  the same URL into Settings → Network on **both** PCs.

## "Do I need a pairing code?"
- No. v1.0.5 removed pairing codes from the assisted flow: Address →
  Connect → host Accept popup. Trusted Devices is an address book
  only — it fills the Address field, but host Accept is still required
  every time. The only no-Accept path is Unattended (password, opt-in).

## Taskbar / desktop icon still shows the old (default) icon
- v1.0.5 ships a multi-size icon (16–256) + desktop icon ON by default.
- If Windows still shows the old icon after an upgrade: **uninstall the
  old version first**, then install the new one. Windows caches icons —
  clear the cache (`ie4uinit.exe -show` in Run), log out/in, and
  unpin/re-pin the taskbar shortcut if you pinned the old EXE.

## Installer: "Setup was unable to automatically close all applications" / "DeleteFile failed; code 5. Access is denied."
- Cause: the OLD RemoteDesk.exe was still running, so Windows locked
  its file and the installer could not replace it. The old UI stayed
  because the new version never actually got installed.
- v1.0.6+ fix: the installer auto-closes the running app (Restart
  Manager) before replacing files, so this should not happen anymore.
- If it still happens on an older installer: close RemoteDesk fully
  (right-click its tray icon → Exit, or Task Manager → End task on
  RemoteDesk.exe), or uninstall the old version first, then install.

## LAN scan finds nothing
- Hosts must have hosting ON. Some routers block UDP broadcasts — use manual
  IP entry instead (always works if the network allows it).

## Update popup never appears
- `UPDATE_REPO` in `app/config.py` must be the real `OWNER/REPO`, not the
  placeholder, and a newer `vX.Y.Z` Release must exist on GitHub.
- The app checks at most once a day automatically — use "Check for Updates now".
- Drive links do NOT trigger popups (Drive has no version API) — by design.

## App won't start / module missing
- Run from source: `pip install -r requirements.txt` (Python 3.11).
- On the packaged EXE: reinstall from the latest installer.

## Installer / SmartScreen warning
- v1 is not code-signed; Windows may show "Windows protected your PC" →
  "More info" → "Run anyway". Expected until code signing is added.
