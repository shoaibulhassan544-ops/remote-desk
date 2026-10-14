# UI/UX & Screen Flow — RemoteDesk v1.0.2 (VIP)

Style (v1.0.2): premium VIP design. Window 1000×680, minsize 860×600.
Left sidebar navigation (deep navy in dark mode), main content area with
rounded-card feel via padded frames, top header with product mark + version +
status pill (Idle / Hosting ON / Connected). Dark premium theme by default:
deep navy #0B1220 background, card #16203A, gold accent #E8B84B for primary
buttons, teal #14B8A6 secondary. Light theme available via instant toggle —
no restart needed; the toggle re-skins sidebar/cards/header immediately.
Typography: Segoe UI. Every button is wired to real code or explicitly
disabled with a reason — no fake "connected" states.

## Screens (single window, sidebar)

### 1. Dashboard
- Card "This device": Your ID (grouped), device name, status line, hosting
  toggle, pairing-code display + "Generate new code", expiry note.
- Card "Connect to a remote device": host IP, port, pairing code / unattended
  password field, "Use unattended password" checkbox, Connect / Disconnect /
  Scan LAN buttons.
- Card "How to connect — 4 steps": 1) On the laptop to CONTROL (host):
  Start Hosting, Generate pairing code. 2) Note its IP (Diagnostics / ipconfig)
  + pairing code. 3) On YOUR laptop: enter IP + port 47900 + pairing code →
  Connect. 4) Host clicks Accept (+ ticks Control). Plus: "No username needed.
  Both laptops must be on the same Wi-Fi. For your own laptop, enable
  Unattended access in Security so no Accept click is needed."
- Card "Activity log": scrolling log of real events.

### 2. Viewer
- Status line (Not connected / Connected to …).
- Black canvas showing live JPEG frames (scaled to window).
- Mouse move/click/scroll forwarded ONLY when control is granted.
- Note button: "Control is granted by the host" (no self-grant path).

### 3. File Transfer
- Explains permission gating + "never auto-executes".
- Status line; "Send a file…" (requires active session + permission).

### 4. Trusted Devices
- List (name — ID), "Remove selected (revoke)".

### 5. History
- Session history text list (timestamps, outcomes).

### 6. Security (Unattended Access)
- Opt-in checkbox, new-password field, "allow control in unattended" checkbox,
  Save button. Explains hash-only storage.
- "End active session now" safety button.

### 7. Diagnostics
- "Run diagnostics": product/version, device ID, port, capture/input availability,
  hosting state, session state, relay note. Troubleshooting pointer.

### 8. Settings & About
- Download folder picker, clipboard-sync toggle, Save.
- Updates card: "Check for Updates now".
- About card: name, version, "Developed by Shoaib Azeez", description.

## Dialogs (modal)
- **Incoming Connection Request:** requester name/ID/IP, "Only accept if you know
  and trust this person", checkboxes (control, file transfer), Accept / Reject.
  Gold Accept, red Reject (VIP styling).
- **Update available (v1.0.2 in-app download):** new version tag, changelog,
  progress bar + status line, buttons:
  [Download Update] → downloads the `Setup-RemoteDesk-*.exe` asset inside the
  app (threaded, live progress, cancellable by closing the dialog) to
  `~/Downloads/RemoteDesk-Updates/` →
  on success [Run Installer] becomes enabled and launches the downloaded file
  ONLY on user click (never auto-executes) + [Later].
  If no installer asset exists or the download fails: status shows the error
  and [Open release page] (browser) is the fallback, with a note why.

## Screen flow
```
Sidebar: Dashboard ── Connect ──► Viewer (live frames)
    │  ▲                             │ Disconnect
    │  └── Hosting ON ──► Incoming Request dialog ── Accept ──► banner + stream
    ▼
Security / Trusted / History / Files / Diagnostics / Settings & About
```
## Error / empty states
- Connect failure → status pill + log show the concrete reason.
- No LAN devices found → log explains hosting must be ON + broadcast caveat.
- Capture unavailable → viewer stays "Not connected", diagnostics say why.
- Update check with repo unconfigured → "not configured yet" message, no crash.
- Update download failure → status shows the error + browser fallback offered.
