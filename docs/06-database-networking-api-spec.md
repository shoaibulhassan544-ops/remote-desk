# Database, Networking & API Specification — RemoteDesk v1.0.0

## 1. Storage (no database server — JSON files)
Location: `%APPDATA%/RemoteDesk/` (Windows) or `~/.config/RemoteDesk/` (dev).

| File | Contents | Secrets? |
|---|---|---|
| `device.json` | device_id, device_name | No |
| `settings.json` | theme, port, download_dir, clipboard_sync, unattended_enabled, unattended_password_hash, unattended_allow_control, hosting_enabled | Hash only, never plaintext password |
| `trusted_devices.json` | [{device_id, device_name, note, added_at}] | No |
| `history.json` | last 500 session entries [{ts, peer, direction, outcome}] | No |
| `audit.json` | reserved for future persistent audit (v1 keeps audit in memory) | No |
| `device_cert.pem` / `device_key.pem` | per-device self-signed TLS cert + private key | Key file 0o600 |

Schema changes: additive only; unknown keys ignored on load.

## 2. Ports
| Port | Protocol | Purpose |
|---|---|---|
| 47900 (configurable) | TCP + TLS | Session: auth, screen frames, input, files |
| 47901 | UDP broadcast | LAN discovery announcements (presence only) |
| 47902 | TCP (stub only) | Dev-only signaling stub — NOT production |

## 3. Wire protocol (session channel)
- Framing: 4-byte big-endian length N + N bytes UTF-8 JSON. Max frame 8 MB.
- Envelope: `{"type": str, "seq": int, "ts": float, "payload": {...}}`
- All traffic inside TLS. Message types:

| Type | Direction | Payload | Notes |
|---|---|---|---|
| `hello` | guest → host | {device_id, device_name} | First message |
| `auth` | guest → host | {method: "pairing", code} or {method: "unattended", password} | Password/code inside TLS only |
| `auth_ok` | host → guest | {host_id, host_name, control, file_transfer} | After consent + auth |
| `auth_failed` | host → guest | {reason} | Generic-ish reason; no user enumeration |
| `request_control` | guest → host | {} | Reserved; v1 control comes from Accept dialog |
| `permission_update` | host → guest | {control, file_transfer} | Reserved for mid-session changes |
| `screen_frame` | host → guest | {jpeg_b64, w, h} | JPEG bytes base64 |
| `input_event` | guest → host | {event: {kind, ...}} | Applied only if control granted |
| `clipboard` | both | {text} | Only if clipboard_sync on + session active |
| `file_offer` / `file_accept` / `file_chunk` / `file_done` / `file_error` | both | {name, size, sha256} / {data_b64} / … | Receiver must accept each offer; chunks 64 KiB |
| `ping` / `pong` | both | {} | Latency measurement |
| `disconnect` | both | {reason} | Clean close |
| `error` | both | {message} | Readable error |

Input event kinds: `move {x,y}`, `click {button, pressed, x, y}`,
`scroll {dx, dy}`, `key {key (single char), pressed}`.

## 4. LAN discovery
- Broadcast packet: `REMOTEDESK-DISCOVERY-v1|<JSON>` where JSON =
  `{magic, device_id, device_name, port}`.
- Sent every 3 s while hosting is ON. Listeners scan ~5 s.
- Discovery advertises presence ONLY — it never grants access.

## 5. Update API (GitHub Releases — no owner server)
- Request: `GET https://api.github.com/repos/<OWNER>/<REPO>/releases/latest`
  with `User-Agent: RemoteDesk-Updater`. No auth needed for public repos.
- Response fields used: `tag_name` (e.g. `v1.1.0`), `name`, `body` (changelog),
  `html_url` (release page).
- Client rule: `parse_version(tag) > parse_version(current)` → show popup.
- Failure modes: repo unconfigured / network error / malformed response →
  return None (no popup, no crash). See `app/update_checker.py`.

## 6. Internet mode (NOT in v1 — spec for future)
- Direct internet: host port-forward 47900 or VPN. Documented only.
- Relay: deploy coturn (STUN/TURN) per docs/TURN-DEPLOYMENT.md + a real
  authenticated signaling server (the included stub is dev-only and must not
  be used). Screen traffic via TURN relay must remain end-to-end TLS.
