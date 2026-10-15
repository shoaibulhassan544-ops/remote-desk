# Troubleshooting — RemoteDesk v1.0.11

## Connect nahi ho raha — Device ID nahi mila / IP se bhi connect nahi ho raha (fixed in v1.0.11)

- **Pehle Connection Test dabao** (Home ya Remote Control pe, Connect
  ke paas). Wo 4 steps dikhata hai — 1) Address resolve 2) TCP
  connect 3) TLS handshake 4) Host jawab — har step PASS/FAIL, saaf
  lafzon me. Jo step FAIL ho, uski detail me uska fix likha hota hai.
- **Device ID (Address) nahi mila?** Checklist:
  1) **Dusre PC pe Start Hosting ON hai?** (Home → HOST THIS PC →
     Start Hosting — bina iske dusra PC connect nahi ho sakta.)
  2) **Dono PC ek hi Wi-Fi pe hain?** (Alag Wi-Fi / mobile hotspot
     pe LAN discovery kaam nahi karti — phir IP ya Signaling Server
     chahiye.)
  3) **Dusre PC pe Windows Firewall me RemoteDesk Allow hai?**
     Settings → Network → Windows Firewall → "Windows Firewall me
     Allow karo" (Admin prompt me Yes dabao). Ya installer ye rule
     khud bana deta hai.
  4) **Find on LAN** dabao — agar device list me aa jaye to usko
     select karo.
  Phir bhi nahi? Us PC ka **IP address** likh ke Connect dabao.
- **IP se bhi connect nahi ho raha?** Sab se common wajah Windows
  Firewall hai (upar step 3). Dusri wajah: dusre PC pe Hosting OFF
  hai, ya IP galat hai (dusre PC ke Home pe uska LAN IP likha hota
  hai), ya dono PC alag network pe hain. Connection Test ka step 2
  (TCP) FAIL hoga to Firewall/Hosting hi wajah hai; step 3 (TLS)
  FAIL hoga to dono PC pe version alag hai — dono pe latest
  RemoteDesk install karo.
- **"Host ne connection mana kiya"?** Dusre PC pe Start Hosting ON
  karo + Firewall me Allow karo (upar step 3).
- **"Host tak pahuncha nahi (timeout)"?** IP sahi hai? Dono PC ek hi
  Wi-Fi pe hain? Firewall me Allow hai?

## "Failed to load Python DLL ... python311.dll: LoadLibrary: The specified module could not be found" (portable EXE)
- WHAT IT MEANS: the portable EXE is a self-extracting bundle — on
  first run it unpacks Python + all libraries into a temp folder
  (`%TEMP%\_MEIxxxxxx`) and loads `python311.dll` from there. This
  error means that unpack/load step failed, NOT that your PC is
  missing Python (the EXE carries its own Python).
- MOST LIKELY CAUSES (in order):
  1. **Incomplete / corrupt download** — the ~20 MB file got cut off
     (browser/Drive hiccup). Re-download fresh and check the size.
  2. **Antivirus blocking the temp extraction folder** — some AVs
     quarantine the unpacked DLLs. Add an antivirus exclusion for
     RemoteDesk, or pause AV for the first run only.
  3. **Missing VC++ Redistributable 2015–2022 (x64)** on the PC —
     the bundled runtime needs it. Install it from Microsoft, then
     run RemoteDesk again.
  4. **Stale temp folders** — delete `%TEMP%\_MEI*` folders and retry.
- FIXES THAT WORK:
  - Prefer the **Setup installer** (`Setup-RemoteDesk-*.exe`) over the
    portable EXE — it installs the files properly instead of
    extracting to temp every run, so this error basically never
    happens with it.
  - Re-download, clear `%TEMP%\_MEI*`, install VC++ Redist 2015–2022
    x64, allow RemoteDesk in antivirus.
- PREVENTION (v1.0.10+): CI now smoke-tests BOTH the built EXE and
  the installed EXE with `--version` on a real Windows runner
  BEFORE any release publishes (see `.github/workflows/build.yml`),
  and UPX compression is disabled — UPX-compressed onefile bundles
  are a known cause of AV interference + DLL load failures.

## App lags / jerky scrolling / lag on tab switch (fixed in v1.0.10)
- ROOT CAUSE (pre-v1.0.10): every tab switch rebuilt the trusted /
  history / file lists (disk reads + destroy/recreate of every row);
  refresh helpers reconfigured widgets even when nothing changed;
  the viewer redrew every frame at full host rate.
- Fix in v1.0.10: only the shown page refreshes, and only when data
  changed; no-op refreshes are skipped; viewer frames capped at
  ~15 fps with identical-frame skip; update check deferred until
  after first paint. Scrolling moves one equal step per wheel notch.
- If scrolling still feels jumpy on a very slow PC: close other heavy
  apps — the viewer + CTk redraws are the heaviest part.

## "Upgrade asks to uninstall first / Access denied" (fixed in v1.0.9)
- ROOT CAUSE (pre-v1.0.9): the update flow showed a manual installer
  button while the app stayed OPEN, so Windows locked RemoteDesk.exe
  and the installer could not replace it — the user had to uninstall
  first. The install folder itself never changed (same folder since
  v1.0.5); the lock was the whole problem.
- Fix in v1.0.9: after the update downloads, the popup shows
  [Install Now] + a 3-second countdown, then the installer launches
  detached and the app closes itself BEFORE the installer runs —
  nothing is locked, the upgrade replaces files in place, no
  uninstall needed. Clicking [Later] cancels the auto-install.
- If you run the installer MANUALLY while the app is open: close
  RemoteDesk first (or let the installer's ssInstall taskkill close
  it), then run the installer — still no uninstall needed.

## "Address pe connect nahi ho raha, IP pe ho raha hai" (fixed in v1.0.7)
- ROOT CAUSE (pre-v1.0.7): the host never broadcast its presence
  (`DiscoveryBroadcaster` was never started), so LAN scan found nothing
  and a Device ID could never resolve on LAN.
- Fix in v1.0.7: hosting now broadcasts presence (LAN + loopback).
  Make sure BOTH PCs run v1.0.7+, hosting is ON on the host, and both
  are on the same Wi-Fi/LAN. If LAN scan still finds nothing (some
  routers block UDP broadcasts), type the host's IP directly, or use
  the signaling server (docs/SIGNALING_DEPLOY.md) on both PCs.

## "IP pe connect ho gaya par screen / mouse / folders / full access nahi" (fixed in v1.0.7)
- ROOT CAUSES (pre-v1.0.7): (1) the host's Accept popup had Control
  defaulted OFF → the session was view-only and clicks did nothing.
  (2) The viewer sent raw canvas coords while the host treated them as
  absolute screen coords → clicks landed in the wrong place.
- Fix in v1.0.7: Control defaults ON in the Accept popup (host can
  still untick it), and clicks are scaled to the host's real screen
  size. If clicks still do nothing: check the viewer toolbar shows
  "Control: ON" — if it says OFF, the host unticked Control; reconnect
  and have the host keep Control ON when Accepting.

## Update popup: empty "What's new" / clipped "Later" button (fixed in v1.0.7)
- ROOT CAUSE: GitHub Releases created via the web UI have an EMPTY
  body, so the popup showed a blank box; the old popup layout also
  clipped the Later button at the edge.
- Fix in v1.0.7: small popup (~520×420) with ONLY [Download Update]
  [Later], and a built-in changelog so "What's new" is never blank.

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
- v1.0.7 ships a multi-size icon (16/24/32/48/64/128/256) + desktop icon
  ON by default. The installer now ships `icon.ico` as a file and BOTH
  shortcuts point at it directly (`IconFilename`), so the desktop icon
  shows our logo even if EXE embedding ever fails. The CI build FAILS
  if the EXE has no icon resources, so a bad icon can never ship
  silently again.
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
- v1.0.7+ fix: on top of Restart Manager, the installer now silently
  force-closes `RemoteDesk.exe` (`taskkill /F`, errors ignored) right
  before files are replaced — fully automatic, no popup, even if the
  Restart Manager dialog would have appeared.
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
