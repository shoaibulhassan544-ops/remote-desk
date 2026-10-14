# BUILD_EXE.md — Get the Windows installer (.exe)

This Linux machine **cannot** build a Windows .exe. The real build happens
on GitHub Actions (Windows) — same two-route pattern as Shoaib's other tools.

## Route A (recommended): GitHub Actions + Release

1. Create a GitHub repo (e.g. `remote-desk`) and push this project.
2. In `app/config.py`, set `UPDATE_REPO = "shoaibulhassan544-ops/remote-desk"` (already done in v1.0.0).
   (Also update the version in `setup.iss` to match `app/version.py`.)
3. Commit + push, then tag the release:
   ```
   git add -A
   git commit -m "RemoteDesk v1.0.0"
   git push origin main
   git tag v1.0.0
   git push origin v1.0.0
   ```
4. GitHub → Actions → watch the "Build RemoteDesk" run (tests + PyInstaller + Inno Setup).
5. When it finishes, GitHub → Releases → `v1.0.0` contains:
   - `Setup-RemoteDesk-1.0.0.exe` — the installer (give this to users)
   - `RemoteDesk.exe` — portable single-file build
6. Download `Setup-RemoteDesk-1.0.0.exe`, run it, install, done.
7. **Publishing this Release is what makes every installed copy show the
   "New update available" popup.** See docs/SETUP_UPDATE.md.

## Route B: Build on your own Windows PC

1. Install Python 3.11 + Inno Setup 6.
2. Copy this project folder to the PC.
3. Double-click `build.bat` (runs tests, then PyInstaller).
4. Run `iscc setup.iss` → `release\Setup-RemoteDesk-1.0.0.exe`.

## Drive (Google Drive) upload — manual share link only

Drive is **not** connected right now, so this step is pending:
once Drive is connected, upload `Setup-RemoteDesk-1.0.0.exe` to Drive and
share the link so people can download/install manually.

Important: the Drive link is ONLY for manual downloads. Auto-update popups
come from GitHub Releases, not Drive — Drive has no version API, so the app
cannot detect a new file on Drive. Do not point the updater at Drive.
