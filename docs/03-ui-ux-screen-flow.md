# UI/UX & Screen Flow — RemoteDesk v1.0.7 (Option 1 AnyDesk Blue, final flow)

v1.0.7: `app/ui.py` was DELETED and rewritten FRESH from scratch in the
same Option 1 tokens (no leftover v1.0.4/v1.0.5 layout code). Changes vs
v1.0.5: Accept popup Control defaults ON (was OFF); viewer shows
"Waiting for screen…" until the first frame + a "Control: ON/OFF"
indicator; update popup is SMALL (~520×420) with only
[Download Update] [Later] and a built-in changelog fallback.

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

### 1. Home — FINAL v1.0.5 FLOW: Address → Connect → Host Accept
- "Welcome Back!" heading + subtitle.
- Card "YOUR ADDRESS": the 9-digit Device ID in huge text + Copy button,
  device name, OS label from `platform.system()` / `platform.release()`
  (never hardcoded), status (Idle / Hosting ON / Connected), small
  muted line "IP (LAN): … • Public IP (Internet): …".
- Card "HOST THIS PC": Start/Stop Hosting + note that the other PC
  types this PC's Address and the host gets an Accept popup. NO
  pairing code, NO connection-type controls on Home (those live in
  Settings → Network).
- Card "Connect to a remote device": ONLY "Remote Address" Entry
  (Device ID ya IP — placeholder "739 738 074 ya 192.168.1.100"),
  big blue Connect + Disconnect + Find on LAN; Enter key also
  connects. Below: "Unattended (password se)" checkbox — when ticked,
  a password entry appears (the ONLY no-Accept path). Help lines:
  "1) Dusre PC pe Start Hosting dabao, uska Address lo. 2) Yahan
  Address likh ke Connect dabao — dusre PC pe Accept ka popup aayega."
  + "Assisted: host ke popup pe Accept zaroori hai."
  Resolution: IP/hostname → direct; Device ID → LAN scan first,
  then signaling lookup (if URL configured); not found → one simple
  error. Progress states: Resolving… → Connecting… → Waiting for
  host… → Connected. Decline/timeout → "Host ne request decline kar
  di / jawab nahi diya."
- Card "Recent sessions": REAL history from `storage.load_history()`
  (device name + IP + timestamp + status); empty state "No sessions yet."
- Card "Quick actions": File Transfer / Trusted Devices / Settings buttons.
- Card "Activity log": scrolling log of real events.
- Footer: "Developed by Shoaib Azeez".

### 2. Remote Control (Connect page)
- Tabs: Quick Connect / Saved Devices (small buttons switching sub-frames).
- Quick Connect: ONE "Remote Address" entry (Device ID ya IP), Port
  entry, "Unattended (password se)" checkbox (ticking reveals the
  password entry), prominent blue Connect, Disconnect, Scan LAN,
  "Find on LAN", progress/status label with actionable errors, e.g.
  "Host not reachable at X:47900 — check hosting ON, same Wi-Fi for
  LAN, or Public IP + port mapping for Internet". NO pairing-code
  field, NO connection-type dropdown here — advanced options live in
  Settings → Network (Signaling server URL + auto-register, see
  docs/SIGNALING_DEPLOY.md).
- Saved Devices: trusted list = address book (clicking one fills the
  Remote Address entry; host Accept still required every time),
  "Discovered on LAN" list (clicking one fills its IP), Scan LAN button.

### 3. Viewer
- Top toolbar: Connected status, quality indicator (real measured frame
  size + fps from received frames, else "—"), latency "—" (the protocol
  has no round-trip measurement — never a hardcoded ms number),
  Full-screen button (toggles via `root.attributes("-fullscreen", …)`,
  Esc exits), red Disconnect, "Request control (host must allow)" note.
- States driven by real client state: "Connecting…" via status line,
  "Waiting for screen…" until the first frame arrives, then live frames,
  "Not connected — connect from Remote Control."
- Black canvas showing live JPEG frames (scaled to window).
- Toolbar shows a visible "Control: ON/OFF" indicator so the user can
  SEE whether clicks will work.
- Mouse move/click/scroll are scaled from canvas coords → the host's
  real screen size (sent with every frame) and clamped to host bounds,
  forwarded ONLY when control is granted.

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
  (View Screen — checked ON, enabled; Control (Mouse & Keyboard) —
  checked ON by default in v1.0.7, host can still untick it, with the
  label "Control ON rakhne se dusra banda mouse/keyboard use kar
  sakega"; File Transfer — OFF by default, disabled with a note when
  File Transfer is off in Settings), Accept (green) / Decline (red).
  TIMEOUT: no answer in 60 s → auto-reject + log line + dialog closes.
  Unchecking View Screen on Accept is treated as a decline (a session
  without screen sharing is meaningless) and logged as such.
- **Update available (in-app download), SMALL popup ~520×420:** new
  version tag, changelog (built-in fallback when the Release body is
  empty — never blank), progress bar + status line, ONLY TWO buttons:
  [Download Update] → downloads the `Setup-RemoteDesk-*.exe` asset inside
  the app (threaded, live progress, cancellable by closing the dialog) to
  `~/Downloads/RemoteDesk-Updates/` →
  on success the button becomes [Run Installer] and launches the
  downloaded file ONLY on user click (never auto-executes) + [Later]
  stays. If the download fails: status shows the error and a tiny
  "Open release page" text-link appears as the fallback, with a note why.

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
