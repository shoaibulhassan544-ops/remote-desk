# Release Checklist — RemoteDesk

Use for EVERY release (including v1.0.0). All boxes must be ticked.

## Code
- [ ] `app/version.py` bumped; `setup.iss` version matches.
- [ ] `UPDATE_REPO` in `app/config.py` is the real `OWNER/REPO` (not placeholder).
- [ ] No secrets in code, config examples, docs, or logs (grep: password/token/key).
- [ ] No TODO / simulated implementation in a claimed-complete feature.

## Tests
- [ ] `python -m pytest -q` passes (record output in TEST-REPORT).
- [ ] `python -m py_compile` passes on all sources.
- [ ] Pairing / traversal / revocation / rate-limit tests green.

## Verification (manual, on real Windows)
- [ ] Two-PC LAN assisted session end-to-end (Accept, stream, input, disconnect).
- [ ] Rejected request yields no session.
- [ ] Revoked control stops input immediately.
- [ ] File transfer: success + failure + traversal rejection.
- [ ] App restart keeps device ID + settings + trusted devices.

## Packaging
- [ ] GitHub Actions build green on the `v*` tag.
- [ ] `Setup-RemoteDesk-<version>.exe` + `RemoteDesk.exe` in the GitHub Release.
- [ ] Installer: installs, launches, uninstalls cleanly on a fresh Windows VM/PC.
- [ ] Upgrade install over the previous version works.

## Updates
- [ ] Release notes written (they appear in the client popup).
- [ ] Update popup verified: older installed copy → popup → Download opens Release.
- [ ] Drive share link updated with the new installer (manual step).

## Docs
- [ ] TEST-REPORT.md updated with real results.
- [ ] KNOWN-LIMITATIONS.md reviewed; nothing claimed that is not verified.
- [ ] TROUBLESHOOTING.md covers any new failure seen during testing.
