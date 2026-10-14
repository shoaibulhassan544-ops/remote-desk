# Product Requirements Document (PRD) — RemoteDesk v1.0.0

- **Product:** RemoteDesk (TEMPORARY name, rebrandable by the owner)
- **Developer credit:** Developed by Shoaib Azeez
- **Platform:** Windows 10 / Windows 11 (x64). Python 3.11 runtime, packaged.
- **Language:** English UI (v1). Dark + light themes.
- **Audience:** Individuals managing their own computers; people giving/receiving
  authorized remote assistance.
- **Scope of v1.0.0:** LAN MVP — real assisted + unattended sessions on the local
  network, screen streaming, input control, permission-gated file transfer,
  update popup via GitHub Releases. Internet relay is NOT in v1 (see §7).

## 1. Problem
People need to help family/friends or manage their own PCs remotely, without
paying for a commercial tool and without handing a stranger permanent access.

## 2. Goals (v1)
1. A real, working LAN remote-desktop session (not a mock).
2. Consent-first: no session without host Accept (assisted) or valid
   unattended password (unattended, opt-in).
3. Encrypted transport (TLS), no plaintext secrets.
4. Updates without owning a server (GitHub Releases as update source).
5. A Windows installer a non-technical user can run.

## 3. Non-goals (v1)
- Internet relay / NAT traversal production service.
- Multi-session hosting, multi-monitor selection, audio, chat.
- Mobile clients, macOS/Linux clients (protocol is portable; UI is Windows-first).
- Any hidden, silent, or persistent access. Explicitly out of scope, forever.

## 4. Functional summary
| Area | v1 behavior |
|---|---|
| Dashboard | Device ID, name, state, remote entry, Connect, recent + trusted |
| Assisted | Request dialog: Accept/Reject + control/file checkboxes, live banner |
| Unattended | Opt-in, min-10-char password (hash only), revoke/disable |
| Screen | Real-time JPEG stream, resize/full-screen via window, quality indicator |
| Input | Mouse move/click/scroll + keyboard (single chars in v1), permission-gated |
| Files | Permission-gated, progress, traversal rejection, never auto-execute |
| Clipboard | Optional, off by default, session-only |
| Sessions | History, trusted devices, revoke, immediate disconnect |
| Updates | GitHub Releases check → popup (Download / Later) |

## 5. Key flows
1. **Assisted:** Guest enters IP + pairing code → host sees dialog → Accept (+perms)
   → stream starts → host sees banner → either side disconnects → perms revoked.
2. **Unattended:** Owner enables + sets password on their own PC → later connects
   with that password (no dialog) → session runs under unattended rules.
3. **Update:** App start (≤1/day) or manual check → GitHub Releases `latest` →
   newer tag → popup with changelog → Download opens release page / Later dismisses.

## 6. Success criteria (v1)
- Two Windows PCs on one LAN complete an assisted session end-to-end.
- Rejected request never yields a session; revoked control stops input immediately.
- `../` file path is rejected; received file is never executed.
- Update popup appears when a newer GitHub Release exists.
- Installer installs, launches, uninstalls cleanly.

## 7. Out of scope / limitations
- Internet sessions require port-forward/VPN or a future relay deployment
  (docs/TURN-DEPLOYMENT.md). v1 does not claim internet connectivity.
- Screen capture uses `mss` (not Windows Graphics Capture API — see
  docs/04-architecture-tech-decisions.md for why).
- No code signing in v1 (SmartScreen may warn; see KNOWN-LIMITATIONS.md).
