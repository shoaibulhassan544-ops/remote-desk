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

## "Pairing code expired / incorrect"
- Codes expire after 5 minutes and work once. Host: Dashboard → "Generate new
  pairing code" and read the fresh code to the guest.
- After 5 wrong attempts the code locks for 5 minutes — generate a new one.

## "Host rejected the request"
- The host clicked Reject (or ignored the dialog). Ask them to Accept and tick
  the permission checkboxes you need.

## "Unattended access is disabled" / "Invalid unattended password"
- On the host: Security tab → enable unattended access + set a password
  (min 10 chars, letter + digit) → Save. Use that exact password as guest.

## Black / frozen viewer
- Host screen capture may be unavailable (locked screen, secure desktop).
  Unlock the host and reconnect.
- Diagnostics tab → Run diagnostics: check "Screen capture available".

## "Device ID not found on this LAN" / typed a Device ID and it won't connect
- A 9-digit Device ID **alone cannot connect** — there is no directory
  to turn it into an IP address. That is why v1.0.4 **blocks** a bare
  Device ID in the IP field.
- Fix 1 (no server needed): put the host's **IP address** in "Remote IP
  address" (same Wi-Fi: LAN IP; different network: public IP + UPnP /
  port forwarding), or click **Find on LAN** to fill it in.
- Fix 2 (AnyDesk-style): deploy the signaling server
  (docs/SIGNALING_DEPLOY.md), paste the **same URL** into Settings →
  Network on **both** PCs, set Connection type → "Internet (via
  Signaling Server)", then enter the Device ID. The host must have
  registered (Start Hosting with auto-register, or "Register this
  device").

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
