# SETUP_UPDATE.md — Publish an update so every installed copy gets the popup

**You need no server.** Updates come from GitHub Releases (free). The app checks
`https://api.github.com/repos/shoaibulhassan544-ops/remote-desk/releases/latest` and compares the
release tag against its own version.

## One-time setup
1. Create a GitHub repo `remote-desk` (public, so clients can check it
   without a token) at https://github.com/shoaibulhassan544-ops/remote-desk.
   Repo MUST stay public: the in-app update checker calls the public GitHub
   Releases API without auth, so a private repo would break the update popup
   for other users.
2. Push this project to it.
3. `app/config.py` already has `UPDATE_REPO = "shoaibulhassan544-ops/remote-desk"`.
   Also set the version in `setup.iss` to match `app/version.py`.
4. Commit + push.

## Publishing a new version (do this for EVERY release)
1. Bump the version in `app/version.py` (e.g. `VERSION = "1.1.0"`).
2. Update `setup.iss` `#define MyAppVersion` to the same number.
3. Write changelog notes (what changed) — they appear in the user's popup.
4. Commit + push, then tag + push the tag:
   ```
   git add -A
   git commit -m "RemoteDesk v1.1.0"
   git push origin main
   git tag v1.1.0
   git push origin v1.1.0
   ```
5. GitHub → Actions → wait for the build (tests + PyInstaller + Inno Setup).
6. GitHub → Releases → `v1.1.0` now exists with `Setup-RemoteDesk-1.1.0.exe`.
   **This Release is the trigger.** Within a day (or on manual "Check for
   Updates"), every installed copy shows:
   > "New update available: v1.1.0 — [Download Update] / [Later]"
   Download opens the Release page; the user installs the new installer.

## Rules that must not be broken
- The tag MUST be `vX.Y.Z` and MUST be newer (semver) than the previous tag,
  or clients will not see the popup.
- Never delete the latest Release — clients compare against it.
- Never point the updater at Google Drive: Drive has no version API, so the
  app cannot detect a new Drive file. Drive is only for manually sharing the
  installer download link.
- Never auto-install updates silently in v1: the user downloads + runs the
  installer themselves (no silent code execution).

## Testing the popup before telling users
1. Publish a test Release (e.g. `v1.0.1`) with any tiny change.
2. On an installed copy of v1.0.0: Settings & About → "Check for Updates now".
3. Confirm the popup shows v1.0.1 + changelog + Download opens the Release page.
