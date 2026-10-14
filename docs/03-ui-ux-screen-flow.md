# UI/UX & Screen Flow — RemoteDesk v1.0.0

Style (per owner's taste): compact window (860×620), rounded-card feel via
padded labelled frames, consistent spacing, tabbed layout, dark/light toggle.
Typography: Segoe UI. Every button is wired to real code or explicitly
disabled with a reason — no fake "connected" states.

## Screens (single window, tab bar)

### 1. Dashboard
- Left card "This device": Your ID (grouped), device name, hosting toggle,
  pairing-code display + "Generate new code", expiry note.
- Card "Connect to a remote device": host IP, port, pairing code / unattended
  password field, "Use unattended password" checkbox, Connect / Disconnect /
  Scan LAN buttons.
- Card "Activity log": scrolling log of real events.
- Status line: "Idle / Hosting ON / Connected / Connection failed: <reason>".

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
- **Update available:** new version tag, changelog, [Download Update] (opens
  release page in browser) / [Later].

## Screen flow
```
Dashboard ── Connect ──► Viewer (live frames)
    │  ▲                     │ Disconnect
    │  └── Hosting ON ──► Incoming Request dialog ── Accept ──► banner + stream
    ▼
Security / Trusted / History / Files / Diagnostics / Settings & About
```
## Error / empty states
- Connect failure → status line + log show the concrete reason.
- No LAN devices found → log explains hosting must be ON + broadcast caveat.
- Capture unavailable → viewer stays "Not connected", diagnostics say why.
- Update check with repo unconfigured → "not configured yet" message, no crash.
