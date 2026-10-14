# Security & Threat Model — RemoteDesk v1.0.5

> v1.0.5 FINAL FLOW: assisted sessions ALWAYS need host Accept. No
> pairing code, no auto-accept (not even for trusted devices). Trusted
> Devices is an address book only. Unattended (password, opt-in) is
> the only no-Accept path.

## 1. Security principles
- Consent-first. Least privilege. No security by obscurity.
- No custom crypto: TLS (stdlib ssl) + PBKDF2-HMAC-SHA256 + OS file permissions.
- No hardcoded credentials. No plaintext secrets on the wire or in logs.
- Never disable Defender, bypass UAC, conceal the process, or evade security software.
- No backdoor, hidden access, silent enrollment — enforced by design (the host
  dialog is the only path to an assisted session; unattended requires the
  owner's explicit opt-in + password).

## 2. Assets
- Host screen content + input control (highest sensitivity).
- Unattended password hash, TLS private key.
- Trusted-device list (address book only), session history, transferred files.

## 3. Threats & mitigations
| ID | Threat | Mitigation | Residual risk |
|---|---|---|---|
| T1 | Stranger connects uninvited | Host Accept popup ALWAYS required for assisted sessions (Accept/Decline + per-permission checkboxes, 60 s auto-reject); no code, no auto-accept; unattended needs password | Host must check the requester name/ID/IP in the popup before Accepting |
| T2 | Request spam / Accept fatigue | 60 s auto-reject; per-IP rate limit; host can Disconnect instantly; session banner always visible | Repeated popups could pressure a careless host — host must Decline unknown requesters |
| T3 | Eavesdropping on LAN | TLS 1.2+ encrypts all frames/files/input | Self-signed cert: first-connect TOFU — a LAN attacker with ARP spoofing could present a fake cert; host Accept popup still required, and host should verify the guest out-of-band |
| T4 | Malicious file path (`../`) | `is_safe_relative_path` + `safe_join` enforced; receiver validates | None known; covered by tests |
| T5 | Received file auto-executed | Never executed; written to download dir only | User might manually run a malicious file — UI warns |
| T6 | Control after revocation | `session.revoke()` checked before every input event; session end revokes all | None known; covered by tests |
| T7 | Stolen unattended password | Hash-only storage; min 10 chars + letter/digit | Weak passwords still guessable — user education in UI |
| T8 | Stolen TLS private key | 0o600 file perms; per-device cert | Key theft alone does NOT grant access — assisted sessions still need host Accept; unattended still needs the password |
| T9 | Secrets in logs | Audit log allows only IDs/outcomes/permission changes; code never logs secrets | None known (grep audit: no password/token/key/screen) |
| T10 | Session hijack / replay | TLS session; 8-h session TTL; disconnect closes sockets | No per-message nonce in v1 — documented limitation; TLS provides transport-level protection |
| T11 | Malformed protocol messages | `validate_message` + frame size cap (8 MB) + guarded decode | None known; covered by tests |
| T12 | Signaling stub abused | Stub is dev-only, no auth, never proxies data, must not be internet-exposed | If someone exposes it, device IDs could be enumerated — README + stub banner warn |

## 4. Assumptions
- The host machine's OS account is trusted (anyone logged in can Accept).
- The host verifies the requester (name + Device ID + IP) in the popup
  before Accepting; unknown requesters must be Declined.
- Windows Firewall may need an allow rule for port 47900 (installer/docs note).
- LAN is semi-trusted; internet direct mode needs UPnP/port forwarding.

## 5. Security checklist (release gate)
- [ ] No secrets in code, config examples, or logs (grep verified).
- [ ] Assisted (request + Accept/Decline) + unattended tests pass.
- [ ] Path-traversal tests pass.
- [ ] Permission-revocation tests pass.
- [ ] Update channel is HTTPS GitHub API only.
- [ ] Known limitations published (docs/KNOWN-LIMITATIONS.md).
