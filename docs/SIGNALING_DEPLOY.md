# Signaling Server — Deploy Guide (RemoteDesk v1.0.4+)

## What this server is

A tiny **directory** that makes AnyDesk-style Device-ID connect work:

1. Host PC registers: `POST /register {device_id, device_name, port}`.
   The server records the IP the request came from.
2. Controller looks up: `GET /lookup?device_id=739738074` → `{ip, port, device_name}`.
3. Controller connects **directly** to that IP over the existing TLS +
   pairing-code session. The host still has to Accept (or have
   unattended access enabled).

What it is **NOT**:
- **NOT a relay** — screen / input / file traffic never passes through it.
- **NOT authentication** — it never sees a pairing code or password.
- **NOT private by itself** — anyone who knows the URL can look up a
  registered ID and learn its IP. Keep the URL private (treat it like
  a phone book, not a vault).

## Why you need it

Without a signaling server, a 9-digit Device ID **cannot** resolve to
an address. That was the v1.0.3 bug: the Connect box said "Device ID or
IP", the user typed a Device ID, and the app could only answer
"not found on this LAN". In v1.0.4 the IP field rejects a bare
Device ID outright, and Device-ID connect works **only** when both
PCs point at the same signaling server.

## Option A — Render (free tier, easiest)

1. Push this repo to GitHub (it already contains `render.yaml`).
2. Render dashboard → **New +** → **Web Service** → pick the repo.
   Render reads `render.yaml`: `python server/signaling_server.py`
   with `$PORT`. Free tier is fine for a personal directory.
3. Copy the service URL, e.g. `https://remotedesk-signal.onrender.com`.
4. Test from any terminal:
   ```bash
   curl https://remotedesk-signal.onrender.com/health
   # {"ok": true, "service": "remotedesk-signaling", "devices": 0}
   ```

Free-tier note: Render spins the service down after inactivity, so the
first lookup after a pause can take ~30 s. For instant lookups, use a
paid instance or Option C.

## Option B — PythonAnywhere (free tier)

1. Create a free account, open a **Bash** console:
   ```bash
   git clone <your-repo-url> remotedesk
   cd remotedesk
   ```
2. PythonAnywhere free accounts only expose web apps through their
   WSGI setup, not arbitrary ports — so instead run the server via a
   small WSGI wrapper is **not** supported by this stdlib server.
   **Use Option A or C** unless you are comfortable writing a WSGI
   adapter yourself. (This is stated plainly so nobody wastes an
   afternoon: the stdlib `http.server` build is meant for Render /
   VPS / a home machine, not PythonAnywhere's WSGI-only free tier.)

## Option C — Any VPS / home machine (always-on)

```bash
# On the server machine (Python 3.11+, no dependencies):
git clone <your-repo-url> remotedesk
cd remotedesk
PORT=47902 nohup python3 server/signaling_server.py --host 0.0.0.0 &
# If the machine is behind a router, forward TCP 47902 to it,
# or put it behind nginx/Caddy with TLS and use the https URL.
```

## Pointing both PCs at the server

On **each** PC, in RemoteDesk: **Settings → Network → Signaling server**
→ paste the **same** URL (e.g. `https://remotedesk-signal.onrender.com`)
→ **Save signaling settings** → tick **"Register this device when
hosting starts"**.

Then:
- **Host PC:** Start Hosting → it auto-registers (or click
  **Register this device** on Home / Remote Control).
- **Controller PC:** Connection type → **"Internet (via Signaling
  Server — needs server URL)"** → enter the host's **Device ID** →
  Pairing code → **Connect**. The app looks the ID up, gets the IP,
  and connects normally.

## API reference

| Method | Path | Body / query | Success | Failure |
|---|---|---|---|---|
| POST | /register | `{device_id, device_name, port}` | 200 `{ok, peer}` | 400 bad input, 429 rate-limited (1 per ID per 10 s) |
| GET | /lookup?device_id=XXX | — | 200 `{ok, peer}` | 404 `{ok:false, error}` |
| POST | /unregister | `{device_id}` | 200 `{ok, removed}` | — |
| GET | /health | — | 200 `{ok, devices}` | — |

`peer` = `{device_id, device_name, ip, port, updated_at}`.
Entries older than 24 h are pruned. Registry persists to
`server/signaling_registry.json` (or `$SIGNALING_DATA_FILE`).

## Curl test commands

```bash
BASE=https://remotedesk-signal.onrender.com   # your URL here

# Register a test device (pretend you are the host):
curl -s -X POST $BASE/register -H 'Content-Type: application/json' \
  -d '{"device_id":"739738074","device_name":"TEST-PC","port":47900}'

# Look it up (pretend you are the controller):
curl -s "$BASE/lookup?device_id=739738074"

# Unknown ID -> 404:
curl -s "$BASE/lookup?device_id=000000000"

# Clean up:
curl -s -X POST $BASE/unregister -H 'Content-Type: application/json' \
  -d '{"device_id":"739738074"}'
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Signaling server URL set nahi hai" | URL empty in Settings | Paste the URL on **both** PCs, Save |
| "Device ID signaling server pe nahi mila" | Host never registered, or PCs use different URLs | Host: Start Hosting with auto-register on, or Register now; confirm the URL matches on both PCs |
| Lookup slow on Render free tier | Service was spun down | Wait ~30 s and retry, or use a paid/always-on host |
| "Host not reachable at IP:port" after a successful lookup | Host's port not reachable (firewall / no UPnP / no port-forward) | Host: allow RemoteDesk through Windows Firewall; use UPnP or port-forward TCP 47900 |
