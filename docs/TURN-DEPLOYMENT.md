# TURN / STUN Deployment Guide — RemoteDesk (future internet mode)

Status: **NOT deployed, NOT in v1.** This guide exists so internet mode can be
added later without redesigning. v1 is LAN-direct only.

## Why TURN is needed
Two PCs on different networks usually cannot connect directly (NAT/firewall).
STUN lets them discover their public address; when direct connection still
fails, TURN relays the traffic. All relayed traffic stays end-to-end TLS
(the relay sees encrypted bytes only).

## Deployment with coturn (example — replace placeholders, NO real secrets here)
On a small Linux VPS (Ubuntu 22.04+):

```bash
sudo apt update && sudo apt install -y coturn
```

`/etc/turnserver.conf` (example — use YOUR domain, YOUR strong secrets):
```
listening-port=3478
tls-listening-port=5349
listening-ip=YOUR_SERVER_PUBLIC_IP
relay-ip=YOUR_SERVER_PUBLIC_IP
external-ip=YOUR_SERVER_PUBLIC_IP
realm=turn.example.com
server-name=turn.example.com
lt-cred-mech
user=remotedesk:REPLACE_WITH_A_LONG_RANDOM_SECRET
cert=/etc/letsencrypt/live/turn.example.com/fullchain.pem
pkey=/etc/letsencrypt/live/turn.example.com/privkey.pem
no-stdout-log
```

```bash
sudo systemctl enable --now coturn
# Open in cloud firewall: 3478/tcp+udp, 5349/tcp, 49152-65535/udp
```

## Client config (future)
- STUN: `stun:turn.example.com:3478`
- TURN: `turn:turn.example.com:3478` with the `remotedesk` user + secret.
- The app must ship a TURN config screen + a per-deployment credential
  (never a hardcoded shared secret in the public client — use time-limited
  TURN credentials issued by your authenticated signaling server).

## Signaling server (future, authenticated)
- The included `server/signaling_stub.py` is DEV-ONLY (no auth, no encryption)
  and must NEVER be exposed to the internet.
- A production signaling server must: authenticate devices (pairing/unattended),
  validate every message, rate-limit, run over TLS, and issue time-limited TURN
  credentials. It is a separate build + deployment task; do not improvise it
  from the stub.

## Cost note
A small VPS + coturn is typically a few dollars/month. **Ask the owner for
approval before spending anything or deploying a public service** (per the
project's development rules).
