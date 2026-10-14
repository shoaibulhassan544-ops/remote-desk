# Functional Requirements & User Stories — RemoteDesk v1.0.0

## Functional requirements

### Dashboard (FR-D)
- FR-D1: Display stable device ID (9 digits, grouped), device name, online/offline state.
- FR-D2: Remote host + port entry, pairing-code/password entry, Connect button.
- FR-D3: Connection status + readable error messages (never a frozen/blank UI).
- FR-D4: Recent sessions + trusted devices visible.
- FR-D5: Navigation to Settings, Security, File Transfer, About.

### Assisted access (FR-A)
- FR-A1: Host receives a modal request: requester ID + name + IP.
- FR-A2: Host can Accept or Reject. Reject ends the attempt; no session starts.
- FR-A3: Separate checkboxes: Allow control, Allow file transfer.
- FR-A4: Persistent visible "REMOTE SESSION ACTIVE" banner during any session.
- FR-A5: Disconnect button ends the session immediately.
- FR-A6: All session permissions are revoked when the session ends.

### Unattended access (FR-U)
- FR-U1: Disabled by default; enabling requires explicit opt-in + password.
- FR-U2: Password: min 10 chars, letter + digit; stored as salted PBKDF2 hash only.
- FR-U3: Owner can change password, disable unattended access, revoke trusted devices.
- FR-U4: No hidden access, backdoor, silent enrollment, or bypass — by design.

### Remote screen (FR-S)
- FR-S1: Real-time screen frames from the host.
- FR-S2: Viewer resizes with the window; quality/latency shown.
- FR-S3: Adaptive JPEG quality (settings) when capture supports it.
- FR-S4: Reconnect / disconnect handled with readable errors.

### Remote input (FR-I)
- FR-I1: Mouse move/click/scroll + keyboard input while control is granted.
- FR-I2: Input stops immediately when control is revoked or session ends.
- FR-I3: No input accepted outside an authenticated, authorized session.

### File transfer & clipboard (FR-F)
- FR-F1: Send/receive files between authorized devices with progress + done/fail states.
- FR-F2: Path traversal (`..`, absolute paths) rejected.
- FR-F3: Configurable download destination.
- FR-F4: File transfer needs per-session permission.
- FR-F5: Clipboard sync is optional, off by default, session-only.
- FR-F6: Received files are never executed automatically.

### Device & session management (FR-M)
- FR-M1: Trusted devices saved (ID + name + date, no credentials).
- FR-M2: Rename/remove trusted devices; revoke access.
- FR-M3: History: timestamps + outcomes. Logs never contain secrets/screen content.
- FR-M4: Terminate active sessions from the UI.

## User stories
- US-1 (assisted guest): "As a helper, I enter my friend's IP + the code they read
  to me, so I can see their screen after they Accept."
- US-2 (assisted host): "As the person being helped, I see who is asking and choose
  Accept/Reject, and decide whether they may control my mouse."
- US-3 (owner): "As the owner of two PCs, I enable unattended access with a strong
  password so I can reach my second PC without anyone clicking Accept."
- US-4 (owner): "As an owner, I disable unattended access and revoke a device when
  I no longer trust it."
- US-5 (updater): "As a user, when the owner publishes a new version, I get a popup
  offering Download / Later — without the owner running a server."
- US-6 (installer): "As a non-technical user, I download one installer, run it, and
  the app opens."

## Acceptance criteria mapping
Each FR above maps to tests in docs/07-testing-release-plan.md and
`tests/`. A feature is "complete" only when its test passes on real code,
not when its UI renders.
