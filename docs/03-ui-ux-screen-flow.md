# UI/UX & Screen Flow — RemoteDesk v1.0.3 (blue reference)

Style (v1.0.3): professional dark-mode desktop app matching the reference
look. Window 1000×680, minsize 860×600. Left sidebar navigation (fixed
~200 px, app mark + RemoteDesk + version + nav + status pill + theme
toggle + "Developed by Shoaib Azeez"). Deep navy/dark-blue backgrounds
(#0B1220 / #0F1A2E), subtle blue borders/separators (#1E3A5F), BRIGHT BLUE
primary buttons + active nav (#2E7DFF, hover #2563EB), white headings,
muted secondary text (#8CA3C0), modern rounded cards + inputs, clean
compact Windows aesthetic. NO GOLD — gold was removed in v1.0.3 (teal is
gone too; green #22C55E is used only for success/Accept, red #EF4444 only
for danger/Decline). Light theme available via instant toggle — no restart
needed; the toggle re-skins sidebar/cards immediately.
Typography: Segoe UI. Every button is wired to real code or explicitly
disabled with a reason — no fake "connected" states, no fake latency,
no fake 2FA, no fake signaling server.

## Screens (single window, sidebar, stacked frames — no Notebook tabs)

### 1. Home
- "Welcome Back!" heading + subtitle.
- Card "Your Device ID": real device ID formatted in groups of 3
  (e.g. "738 452 910") + Copy button (clipboard), device name, OS label
  from `platform.system()` / `platform.release()` (never hardcoded),
  status (Idle / Hosting ON / Connected).
- Card "Host This PC": Start/Stop Hosting, pairing-code display +
  "Generate new pairing code", expiry note, connection-type radios
  (LAN / Internet), Internet-mode block when Internet is selected
  (Public IP, LAN IP, UPnP status, "Open port (UPnP)", Refresh,
  "Copy connection details", port-forward guide).
- Card "Connect to a remote device": Device ID or IP entry + pairing-code
  entry + "Use unattended" checkbox + blue Connect + Disconnect +
  shared status line. Resolution: IP/hostname → direct; 9-digit ID or
  saved-device name → short LAN discovery scan for its address; anything
  else → "Enter an IP/hostname or pick a Saved Device".
- Card "Recent sessions": REAL history from `storage.load_history()`
  (device name + IP + timestamp + status); empty state "No sessions yet."
- Card "Quick actions": File Transfer / Trusted Devices / Settings buttons.
- Card "Activity log": scrolling log of real events.
- Footer: "Developed by Shoaib Azeez".

### 2. Remote Control (Connect page)
- Tabs: Quick Connect / Saved Devices (small buttons switching sub-frames).
- Quick Connect: Device ID or Name entry, Port entry, Pairing code /
  unattended password entry, "Use unattended password" checkbox,
  connection-type radios (LAN / Internet), prominent blue Connect,
  Disconnect, Scan LAN, progress/status label with actionable errors,
  e.g. "Host not reachable at X:47900 — check hosting ON, same Wi-Fi for
  LAN, or Public IP + port mapping for Internet". Internet-mode block
  (same as Home) when Internet is selected.
- Saved Devices: trusted list (clicking one fills the Device ID entry),
  "Discovered on LAN" list (clicking one fills its IP), Scan LAN button.

### 3. Viewer
- Top toolbar: Connected status, quality indicator (real measured frame
  size + fps from received frames, else "—"), latency "—" (the protocol
  has no round-trip measurement — never a hardcoded ms number),
  Full-screen button (toggles via `root.attributes("-fullscreen", …)`,
  Esc exits), red Disconnect, "Request control (host must allow)" note.
- States driven by real client state: "Connecting…" via status line,
  live frames, "Not connected — connect from Remote Control."
- Black canvas showing live JPEG frames (scaled to window).
- Mouse move/click/scroll forwarded ONLY when control is granted.

### 4. File Transfer
- Tabs: Send Files / Receive Files.
- Send: Choose Files button (real file dialog) + drop-area label
  "Drop files here or use Choose Files" — drag-and-drop ONLY if
  tkinterdnd2 imports (guarded try/except; if missing, the chooser still
  works and DnD is never claimed). Destination device selector (dropdown
  from trusted + history). Transfer queue list.
  **Send is NOT wired in this build:** the Send button shows an honest
  message — "File send over session is not wired in this build — files
  are not sent" — and sends nothing. The chunked protocol exists at
  module level; the UI send path is not connected to a live session.
- Receive: download folder + "Received files land here, never
  auto-executed" + real list (scan of the download folder if it exists,
  else empty state) + Open folder button.
- Recent transfers: real entries if storage has any, else
  "No transfers yet."

### 5. Trusted Devices
- Authorized list: device name + ID + Trusted status dot.
- Buttons: Add Device (dialog: ID + name → saved via storage), Rename
  (prompt for new name, updates storage), Remove (revoke).
- Unattended Access section: Enable toggle + Set/Change Access Password
  (min 10 chars, hash-only, reuses existing unattended logic) + allow
  control checkbox + Save.

### 6. Session History
- Real table from `storage.load_history()`: Device, Type, Duration,
  Status, Date & Time. Search entry filters by device name. Filter
  dropdown: All / Remote Control / File Transfer. Empty state
  "No sessions recorded yet."

### 7. Settings (Security & Settings)
- Tab row: Security / Network / General / About (small buttons switching
  sub-frames).
- Security: Change Access Password (reuses unattended password save,
  hash-only), Two-Factor: DISABLED toggle + note "not implemented in
  this build" (no fake 2FA), Allow Clipboard Sync toggle, Enable File
  Transfer toggle (saved; disabling also disables the file-transfer
  checkbox on incoming requests), "End active session now".
- Network: connection-type default (LAN/Internet radio), Port entry +
  Save, UPnP status label (from `app/internet.py`), Public IP display
  (from `app/internet.py`, "—" on failure), LAN IP, "Open port (UPnP)",
  "Test port reachable" self-test (honest reporting), diagnostics box +
  "Run diagnostics" (includes Internet checks).
- General: download folder picker, theme Dark/Light toggle (instant),
  auto update check toggle, Save.
- About: app mark, "RemoteDesk", version, tagline
  "Connect. Control. Work Anywhere.", "Developed by Shoaib Azeez",
  "Windows 10/11 • Secure & Encrypted" notes, Check for Updates button
  + update popup (existing in-app download logic unchanged).

## Dialogs (modal)
- **Incoming Connection Request:** requesting device name + ID + IP,
  "Only accept if you know and trust this person", checkboxes
  (View Screen — checked, enabled; Control (Mouse & Keyboard);
  File Transfer — disabled with a note when File Transfer is off in
  Settings), Accept (green) / Decline (red). TIMEOUT: no answer in 60 s
  → auto-reject + log line + dialog closes. Unchecking View Screen on
  Accept is treated as a decline (a session without screen sharing is
  meaningless) and logged as such.
- **Update available (in-app download):** new version tag, changelog,
  progress bar + status line, buttons:
  [Download Update] → downloads the `Setup-RemoteDesk-*.exe` asset inside
  the app (threaded, live progress, cancellable by closing the dialog) to
  `~/Downloads/RemoteDesk-Updates/` →
  on success [Run Installer] becomes enabled and launches the downloaded
  file ONLY on user click (never auto-executes) + [Later].
  If no installer asset exists or the download fails: status shows the
  error and [Open release page] (browser) is the fallback, with a note why.

## Screen flow
```
Sidebar: Home ── Connect ──► Viewer (live frames)
    │  ▲                             │ Disconnect
    │  └── Hosting ON ──► Incoming Request dialog ── Accept ──► banner + stream
    │                       (60 s auto-reject)
    ▼
Remote Control / File Transfer / Trusted / History / Settings
```
## Error / empty states
- Connect failure → status line + log show the concrete reason; for
  unreachable hosts the actionable LAN-vs-Internet guidance is included.
- Device ID not found on LAN → "not found on this LAN — check hosting
  is ON … or enter its IP directly".
- No LAN devices found → log explains hosting must be ON + broadcast caveat.
- Capture unavailable → viewer stays "Not connected", diagnostics say why.
- Update check with repo unconfigured → "not configured yet" message, no crash.
- Update download failure → status shows the error + browser fallback offered.
- Public IP lookup failure → "—" (never a fake IP).
- UPnP unavailable/failed → plain message + manual port-forward guide.
