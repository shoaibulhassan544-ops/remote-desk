# TEST REPORT — RemoteDesk v1.0.10 (honest status)

## v1.0.10 addendum (this session) — Home alignment + lag / smoothness

ROOT CAUSES (found by reading app/ui.py, not guessing):
- **New-tab lag:** `_show_page()` rebuilt trusted/history/file lists on
  EVERY switch — disk reads + destroy/recreate of every row — plus
  unconditional pack/pack_forget of the signaling/internet blocks.
  FIX: only the shown page refreshes; `_set_visible()` skips pack ops
  when visibility is unchanged; `_CTkList` gained batch mode (one
  refresh per bulk rebuild instead of O(n^2) per-row configures).
- **Redundant reconfigures:** `_refresh_pill` / `_refresh_nav` /
  `_refresh_history` / `_refresh_home_history` / `_refresh_file_dest`
  reconfigured widgets even when nothing changed. FIX: each caches
  its last state and returns early when identical.
- **Viewer churn:** `_on_frame` decoded + `canvas.delete("all")` +
  recreated the PhotoImage on EVERY incoming frame at full host rate,
  and updated the quality label per frame. FIX: max ~15 fps, skip
  byte-identical frames, reuse one canvas image item, quality label
  at most 2x/sec.
- **Startup:** the update-check network thread started before first
  paint. FIX: deferred to `after(500, ...)`.
- **Scroll:** app adds NO global `bind_all` wheel handlers of its own
  (source guard); CTk's one handler moves exactly one step per notch
  (proven by test: equal steps, zero widget churn while scrolling).
  The scratchy feel was the rebuild/reconfigure churn firing
  alongside scroll redraws, now removed.
- **ALIGNMENT (user's v1.0.8 screenshot):** top cards got
  `rowconfigure(0, weight=1)` + equal row structure (HOST gained
  Status + Port rows mirroring ADDRESS's Status + IP rows); Copy
  button height 36 matches the 32px Device ID text; CONNECT card
  bottom gaps made consistent; Recent/Activity log boxes shortened
  (110→72, 130→88) so the primary cards fit the first screen.
- **SIDEBAR (follow-up):** `side_bottom` padding 16→10 to match nav
  buttons — pill, theme toggle and nav buttons now share ONE left and
  ONE right edge; pill text centered; nav buttons all 40px; active
  pill changes color only, never geometry; pill dot colors:
  green = Idle/Connected, amber = Connecting, red = Error.
- **SETTINGS (follow-up):** new `_settings_row()` grid helper —
  label column left, control column right — applied to the password,
  port, download-folder and connection-type rows.
- **DLL-LOAD HARDENING + CI SMOKE TEST (critical addition):** the
  user hit "Failed to load Python DLL ... python311.dll" on the
  portable EXE — a build that had never been STARTED on Windows.
  FIX: (1) `.github/workflows/build.yml` now runs TWO smoke tests
  on the real Windows runner BEFORE any asset ships — built EXE
  `--version` (exit 0, 60s timeout so a DLL-error dialog fails the
  build instead of hanging) and silent-install (`/VERYSILENT
  /SUPPRESSMSGBOXES /NORESTART /DIR=<temp>`) + installed EXE
  `--version`. (2) `remote_desk.spec`: `upx=False` (UPX onefile
  bundles are a known cause of AV interference + DLL load failures);
  `excludes=[]` kept empty (no VC++ runtime DLLs excluded).
  (3) `run.py` handles `--version` BEFORE importing `app.main`, so
  the smoke test never touches Tkinter. Proven by
  `tests/test_ci_smoke.py` (build.yml contains both smoke steps
  before the release step; subprocess `run.py --version` prints the
  version with rc 0). (4) New TROUBLESHOOTING entry for the DLL
  error (re-download, clear `%TEMP%\\_MEI*`, VC++ Redist 2015–2022
  x64, AV exclusion, prefer the Setup installer).
- **Tests this session:** `python3 -m pytest -q` → **134 passed,
  9 skipped** (129 pre-DLL-hardening + 5 new test_ci_smoke.py;
  9 skipped = 1 pre-existing UDP skip + 8 new live-Tk tests
  skipping without a display and PASSING under Xvfb:
  test_tab_switch_no_rebuild.py ×3, test_refresh_noop.py ×4,
  test_scroll_smooth.py ×2); `python3 run.py --version` → `1.0.10`;
  Xvfb screenshots verified: Home top cards equal height, Copy row
  level, sidebar edges aligned, Settings rows aligned.
- **Honest note:** Home's lower cards (Recent / Quick actions /
  Activity log) still sit below the fold at 1000x680 and scroll —
  the full page cannot fit that height at readable font sizes. The
  primary Address / Host / Connect section fits the first screen,
  and scrolling is now smooth instead of jerky.

## v1.0.9 addendum (this session) — auto-install + clean "What's new" + installer EULA
- **AUTO-INSTALL (user screenshot, v1.0.7→v1.0.8 flow):** the old flow
  showed a manual [Run Installer] button while the app stayed OPEN and
  locked RemoteDesk.exe, so the install failed. FIX: on download
  success the popup shows [Install Now] + a 3-second countdown; at 0
  (or on Install Now) the installer is launched DETACHED
  (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` on Windows,
  `start_new_session` on POSIX) and the app closes itself BEFORE the
  installer replaces files. [Later] cancels the auto-install. The
  installer is NEVER launched while the app is still running.
  Proven by `tests/test_auto_install.py` (detached flags, countdown
  state machine with fakes, Later cancels, no "Run Installer" left).
- **"What's new" GitHub link (user screenshot):** GitHub auto-appends
  "**Full Changelog**: <compare URL>" to release notes and the popup
  showed it. FIX: `sanitize_notes()` in `update_checker.py` drops any
  line with "Full Changelog" / "/compare/" / "github.com", strips
  markdown links to plain text, and falls back to the built-in
  CHANGELOG when nothing readable remains. Proven by
  `tests/test_whatsnew_sanitize.py`.
- **INSTALLER EULA:** new `LICENSE.txt` (authorized use only, consent,
  as-is / no warranty) + `LicenseFile=LICENSE.txt` in `setup.iss`.
  Proven by `tests/test_license.py`.
- **IN-PLACE UPGRADE (no uninstall first):** verified
  `DefaultDirName={autopf}\RemoteDesk` + `PrivilegesRequired=lowest`
  are UNCHANGED since v1.0.5, so every version installs to the SAME
  folder; the past upgrade failures were the running app locking the
  EXE, fixed by the auto-install exit + the ssInstall taskkill backup.
  New TROUBLESHOOTING entry covers it.
- **Tests this session:** `python3 -m pytest -q` → **128 passed,
  1 skipped** (109 pre-v1.0.9 + 19 new: test_auto_install.py ×8,
  test_whatsnew_sanitize.py ×8, test_license.py ×2, plus setup.iss
  license/location guards); `python3 run.py --version` → `1.0.9`;
  `python3 -m py_compile app/*.py` OK; Xvfb smoke (update popup
  flow incl. countdown, all pages, no exceptions).

## v1.0.8 addendum (this session) — CustomTkinter UI rebuild, flows unchanged
- **WHY:** v1.0.7 changed the FLOW but still LOOKED like old flat
  tkinter (user's screenshot: flat rectangles, no card contrast, no
  rounded corners, no depth). Root cause: tkinter native widgets cannot
  look modern no matter the colors. FIX: `app/ui.py` deleted and
  rewritten FRESH on CustomTkinter (same entry points, same handlers,
  same attribute names; all `app/*` logic reused, protocol/security
  untouched). `customtkinter>=5.2.0` added to `requirements.txt`;
  PyInstaller needs no spec change (CustomTkinter ships its own hooks;
  spec still parses; `build.yml` already does `pip install -r
  requirements.txt`).
- **Verified this session:** `python3 -m pytest -q` → **109 passed,
  1 skipped** (103 pre-v1.0.8 + 6 new in `tests/test_ctk_ui.py`:
  CTk imports, entry points + helpers, theme tokens / real card
  separation, no-flat-widget source guard, real update-dict keys,
  v1.0.8 changelog entry); `python3 run.py --version` → `1.0.8`;
  `python3 -m py_compile app/*.py` OK. Xvfb headless smoke test OK
  (build real app, switch all 7 pages + all tab rows, open/close
  Add-trusted dialog + update popup, toggle appearance mode dark →
  light → dark, simulate update progress + failure fallback, no
  exceptions, no zero-size widgets). Real screenshots taken under Xvfb
  (Home + Settings) and inspected: rounded cards with real contrast,
  rounded blue buttons, rounded entries, active nav pill — visibly
  modern vs v1.0.7. One real visual bug found in the first screenshot
  (ghost buttons invisible as plain text on cards) and FIXED (ghost
  fill = border color), then re-screenshotted and re-smoke-tested.
- **Port bugs found + fixed:** (1) UI called non-existent
  `update_checker.download_file` / `release_page_url` and passed
  `check_for_update(VERSION, repo=…)` — corrected to the real API
  (`download_update` + `select_setup_asset`, `check_for_update(current=
  VERSION)`, keys `tag`/`notes`/`url`/`assets`); guarded by a new test
  so it can't regress. (2) The v1.0.7 popup source-guard test required
  old helper names (`_close_update_popup`, `columnconfigure`) — updated
  to guard the same intent (exactly 2 main buttons in the popup,
  release-page link only in the failure path, 520×420). (3) First full
  run showed 3 loopback/discovery failures — proven ENVIRONMENTAL
  (test venv lacked `cryptography`; host TLS cert gen failed), NOT a
  code regression: after `pip install -r requirements.txt` in the venv,
  all pass.
- **NOT yet verified:** real Windows GUI, real 2-PC LAN/signaling test,
  real Windows upgrade run with the app running, in-app download vs a
  real Release. Real-UDP discovery test still skips in this sandbox
  (EPERM) as before.

# TEST REPORT — RemoteDesk v1.0.7 (honest status)

## v1.0.7 addendum (this session) — 3 REAL bug fixes + fresh UI + installer hardening
- **BUG A — Address never resolved on LAN (ROOT CAUSE FOUND):**
  `DiscoveryBroadcaster` was NEVER instantiated in `app/host.py` — the
  host never announced itself, so LAN scan found nothing and a Device ID
  could never resolve. FIX: `HostServer.start()` starts the broadcaster
  (LAN broadcast + loopback, presence-only); `stop()` stops it
  (guarded, idempotent); broadcast failure logs + hosting continues.
  ALSO FOUND: `start()` returned before the server was listening, so an
  immediate connect raced first-run TLS keygen → "Connection refused".
  FIX: `start()` waits on a `_ready` event set after `listen()` (or on
  definitive failure). ALSO FOUND: `DiscoveryBroadcaster` overrode
  `threading.Thread._stop()` with an Event (broke `join()`); renamed to
  `_stop_event`. ALSO FOUND: this sandbox blocks UDP *send* (EPERM),
  so the real-UDP test skips here with a clear reason; packet contents,
  targets, and listener parsing are proven with injected fake sockets
  (and the real-UDP test still runs on Windows / GitHub Actions).
- **BUG B — IP connected but no access (ROOT CAUSES FOUND):** (1) Accept
  dialog Control checkbox defaulted OFF → view-only, clicks did nothing.
  FIX: Control defaults ON (host can still untick), View ON, Files OFF,
  with an explanatory label. (2) Viewer sent RAW canvas coords while the
  host applied them as absolute screen coords, and the host sent
  `w: 0, h: 0` → clicks landed in the wrong place. FIX: host sends real
  screen size in every `screen_frame`; client stores it; UI scales
  canvas → host coords and clamps to host bounds. (3) Frame flow proven
  by LOOPBACK test: host + client in-process on 127.0.0.1, auto-accept
  (control=True) → client received frames AND an input event reached
  the host (test hook, real mouse never moved). Viewer: "Waiting for
  screen…" until first frame + visible "Control: ON/OFF" indicator.
- **BUG C — update popup broken (ROOT CAUSES FOUND):** "What's new"
  empty because web-created Releases have an EMPTY body → built-in
  `CHANGELOG` map in `update_checker.py` (API body → built-in → generic
  line; never blank). "Later" clipped → buttons in a grid with weights
  + padding, popup ~520×420, ONLY [Download Update] [Later]; Download
  starts immediately in-thread with live progress; on success the button
  becomes [Run Installer]; release-page link only as a tiny fallback
  if the download fails.
- **FRESH UI REBUILD:** `app/ui.py` deleted and rewritten from scratch
  (same entry points `RemoteDeskApp(root)`, `run()`), Option 1 AnyDesk
  Blue tokens, no leftover v1.0.4/v1.0.5 layout code. All logic reused
  from `app/*` — protocol/security untouched.
- **Installer hardening (v1.0.7):** `setup.iss` ships `icon.ico` into
  `{app}` + `IconFilename="{app}\icon.ico"` on BOTH shortcuts; `[Code]`
  `CurStepChanged` silently force-closes `RemoteDesk.exe` via
  `taskkill /F` at `ssInstall` (errors ignored) alongside the v1.0.6
  Restart Manager lines; CI "Verify EXE icon" step (pefile,
  RT_GROUP_ICON=14 + RT_ICON=3) FAILS the build if the EXE has no icon
  resources. `icon.ico` rebuilt with 16/24/32/48/64/128/256 (24 was
  missing before).
- **Verified this session:** `python3 -m pytest -q` → **103 passed,
  1 skipped** (79 pre-v1.0.7 + 25 new: discovery broadcast ×5,
  coordinate scaling ×5, loopback session ×2, update popup small ×6,
  setup.iss ×7); `python3 run.py --version` → `1.0.7`;
  `python3 -m py_compile app/*.py` OK; Xvfb headless smoke test OK
  (build app, switch all pages, open update popup — small, two
  buttons, no clipping — no exceptions).
- **NOT yet verified:** real Windows GUI, real 2-PC LAN/signaling test,
  real Windows upgrade run with the app running (installer taskkill
  path), in-app download vs a real Release. Real-UDP discovery test
  skipped in this sandbox (UDP send blocked) — must run on Windows.

---

# TEST REPORT — RemoteDesk v1.0.3 (honest status)

## v1.0.3 addendum (this session)
- Blue reference UI rewrite (app/ui.py): sidebar Home / Remote Control /
  Viewer / File Transfer / Trusted Devices / Session History / Settings;
  deep navy `#0B1220`, card `#13203A`, bright-blue `#2E7DFF` primary +
  active nav; gold removed. Dark default + working Light toggle (instant).
  All v1.0.2 functionality preserved: hosting, pairing, connect, viewer,
  trusted, history, unattended, diagnostics, settings, in-app update
  download. New: Home device-ID card + Copy + real OS label, Recent
  Sessions from real history, Quick Actions; Remote Control Quick
  Connect / Saved Devices tabs + connection-type radios + actionable
  connect errors; incoming-request dialog with View Screen checkbox +
  60 s auto-reject; viewer toolbar with real measured quality (frame
  size + fps) and latency "—"; File Transfer Send/Receive tabs with
  honest "send not wired" message; Trusted Add/Rename/Remove +
  Unattended section; History table + search + filter; Settings
  Security/Network/General/About tabs with disabled 2FA toggle and
  real File Transfer gate on incoming requests.
- Internet (direct) mode (new app/internet.py): `get_public_ip()` (ipify,
  5 s timeout), `get_lan_ip()` (UDP trick), `try_upnp_mapping()` (miniupnpc
  or honest "not installed" fallback), `check_port_reachable()` (bool
  self-test). All never raise. Controller connects with the EXISTING
  direct TCP/TLS `client.connect()` — no protocol change, no signaling
  server, no relay. UI shows Public IP + LAN IP + UPnP status +
  "Open port (UPnP)" + copyable details + port-forward guide, and states
  the CGNAT/strict-router limit plainly.
- History is now actually recorded: outgoing connect → "Connected",
  disconnect → "Ended" with real duration; host Accept → "Accepted"
  (previously `load_history()` was always empty because nothing ever
  appended to it).
- Version bumped to 1.0.3 (app/version.py + setup.iss). Ship only v1.0.3+.
- New tests: tests/test_internet.py (9 tests: ipify plain/JSON parsing,
  failure → None, UPnP fallback when miniupnpc missing, LAN IP string,
  port-reachable open→closed, invalid input → False).
- Verified this session: `python3 -m pytest -q` → **46 passed**
  (37 existing + 9 new); `python3 -m py_compile app/*.py` OK;
  `python3 run.py --version` → `1.0.3`; Xvfb headless smoke test OK
  (construct app, switch all pages, toggle theme twice, Settings/RC/FT
  tabs, build + close update popup, open incoming-request dialog and
  auto-close it without blocking, run diagnostics).
- NOT yet verified: real Windows GUI, in-app download vs a real Release,
  2-PC LAN test, 2-PC Internet test (UPnP + port forwarding on a real
  router), installer install/uninstall. Internet mode is code-complete
  but untested against a real router — UPnP success depends on the
  router, and CGNAT connections will still fail (relay not included).

---

# TEST REPORT — RemoteDesk v1.0.2 (honest status)

## v1.0.2 addendum (this session)
- VIP sidebar UI rewrite (app/ui.py): sidebar + header + status pill +
  instant theme toggle, all previous features kept wired (hosting, pairing,
  connect, viewer, files, trusted, history, security, diagnostics, settings).
- In-app update download (app/update_checker.py + app/ui.py): popup downloads
  the `Setup-RemoteDesk-*.exe` asset in-app with progress bar; Run Installer
  only on user click; browser fallback only when no asset / download fails.
- Version bumped to 1.0.2 (app/version.py + setup.iss) so the installer is
  `Setup-RemoteDesk-1.0.2.exe`.
- New tests: tests/test_update_download.py (asset selection, local-server
  download with progress, failure returns error not raise).
- v1.0.0 installer had the relative-import startup crash; v1.0.1 fixed it via
  run.py. Do NOT ship v1.0.0 / v1.0.1 installers — ship v1.0.2+.
- UI run on real Windows / in-app download against a real Release: NOT yet
  verified (headless VM; must be checked after the v1.0.2 Actions build).

---

# TEST REPORT — RemoteDesk v1.0.0 (honest status)

Date: 2026-10-14. Environment: Linux dev VM, Python 3.12.3.
Nothing below is claimed as verified unless it actually ran.

## Automated tests — IMPLEMENTED AND VERIFIED ✅
Command: `python3 -m pytest -q` → **33 passed in 0.12s**
Command: `python3 -m py_compile app/*.py server/signaling_stub.py tests/*.py` → **OK**

| File | Tests | Result |
|---|---|---|
| test_version_compare.py | parse v-prefix, newer/equal/older, garbage raises | Pass (5) |
| test_path_traversal.py | safe paths, `..`, absolute, `C:\`, safe_join in/out | Pass (6) |
| test_pairing_code.py | accept-once, wrong, expired, lockout, no-code | Pass (5) |
| test_protocol_validation.py | roundtrip, partial, 2 frames, oversize, unknown type, bad seq, b64 | Pass (9) |
| test_rate_limit.py | cap, per-key independence, window expiry | Pass (3) |
| test_session_permissions.py | defaults denied, grant/revoke, end revokes, one-session rule, audit | Pass (6) |

## Integration — IMPLEMENTED AND VERIFIED ✅
- **Loopback TLS host↔guest (127.0.0.1, real sockets + real cert):**
  Host started → pairing code issued → guest connected with code → guest
  reported Connected, host session active → clean disconnect. ✅
- **Rejection path:** guest with no valid code was rejected (no session). ✅
  Note: the rejection message was "Pairing code expired" because no code had
  been issued on that host instance; the wrong-code path itself is covered by
  the unit test above.
- **CLI:** `python -m app.main --version` → `1.0.0` ✅;
  `--check-update` → "No update available (or update checks not configured)" ✅
  (at that time `UPDATE_REPO` was still the `OWNER/REPO` placeholder; it is now set to `shoaibulhassan544-ops/remote-desk` for the v1.0.0 push).
- **UI import:** `import tkinter` OK; full GUI run not done on this headless VM.

## IMPLEMENTED BUT NOT YET VERIFIED ⚠️
- Screen streaming end-to-end on real Windows (capture path needs a real display;
  headless VM has none — `capture_jpeg` correctly returns None there).
- Input injection via pynput on Windows.
- File transfer over a live session (code + protocol ready; no live transfer run).
- Clipboard sync, LAN discovery broadcast, unattended session flow in the GUI.
- Inno Setup script + GitHub Actions workflow (YAML + ISS written; never executed).
- Update popup against a REAL GitHub Release (needs repo + Release).

## PARTIALLY IMPLEMENTED 🟡
- File transfer UI: status + explanation wired; "Send a file…" shows the
  permission note — actual file-picker send is NOT wired in v1 UI.
- Mid-session permission changes (`permission_update` message): protocol type
  reserved; host-side revoke exists in session logic; no UI toggle mid-session.
- `permission_update` / `request_control` messages: defined, not yet used live.

## BLOCKED / NOT DONE 🔴
- **Two-Windows-PC LAN test** — needs 2 physical Windows PCs. Not run.
- **Windows EXE + installer build** — needs GitHub repo + tag push (Actions).
- **Installer install/uninstall/upgrade test** — needs the built installer.
- **Internet connectivity** — no relay deployed; not claimed.
- **Google Drive upload + share link** — Drive not connected; pending owner action.

## Verdict
LAN MVP code is complete and its core logic is tested. The product is NOT
"release-verified" until the 2-PC test + Actions build + installer test pass.
Do not ship to users before those three items are checked off.

## v1.0.4 addendum (2026-10-14) — Device-ID bug fix + signaling server + branding
- `python3 -m pytest -q` → **63 passed** (46 existing + 7 new
  tests/test_signaling.py + 10 new tests/test_connect_validation.py).
- `python3 run.py --version` → `1.0.4`; `setup.iss` MyAppVersion `1.0.4`.
- Xvfb headless smoke test: app constructed, all 7 pages switched,
  connection-type combobox shows all 3 options, split IP/Device ID
  fields present, bare-ID block verified, settings tabs + signaling
  card OK, incoming-request dialog opens + treated as rejected,
  update popup builds + closes, theme toggled twice — no exceptions.
- Signaling server live-checked via curl on localhost: /health,
  /register, /lookup (hit), /lookup unknown ID (404) — all correct.
- Branding: assets/icon.png (512x512), assets/icon.ico (16/32/48/256),
  installer_banner.bmp (164x314), installer_small.bmp (55x58) generated
  with PIL; wired into ui.py (iconphoto/iconbitmap), remote_desk.spec
  (datas + icon), setup.iss (SetupIconFile + wizard images +
  UninstallDisplayIcon).
- Still unverified: real Windows GUI, 2-PC LAN test, 2-PC signaling
  test against a deployed server, installer install/uninstall,
  in-app download vs real Release.

## v1.0.5 addendum (2026-10-14) — FINAL FLOW: Address → Connect → Host Accept
- `python3 -m pytest -q` → **79 passed** (63 v1.0.4 + 6 new
  tests/test_update_popup.py [update-status math, 6-size ICO,
  desktop-icon default ON, embedded PNG] + 10 rewritten
  tests/test_connect_validation.py [Device ID auto-resolve, LAN-first,
  signaling fallback, simple error] + 6 new
  tests/test_assisted_connect.py [request method passes, trusted
  method rejected, unknown rejected, unattended password verified,
  address-book store]).
- `python3 run.py --version` → `1.0.5`; `setup.iss` MyAppVersion `1.0.5`.
- Xvfb headless smoke test: all 7 pages switch, theme toggled twice,
  centered non-resizable update popup builds (footer visible),
  Home single-address box + Unattended toggle present — no exceptions.
- FLOW (final, overrides v1.0.4 pairing-code + v1.0.5-draft trusted
  auto-accept): assisted = Address → Connect → host Accept popup
  (name + ID + IP, View/Control/File checkboxes, Accept/Decline,
  60 s auto-reject). NO pairing code, NO auto-accept. Trusted Devices
  = address book only. Unattended (password, opt-in) = only no-Accept
  path. PairingCodeStore kept only for compatibility.
- UI: Option 1 "AnyDesk Blue" (user-selected). Centered update popup
  with fixed footer (version row, progress + MB/%/speed status,
  Download → Run Installer). Icon: 6-size ICO + desktop icon ON +
  embedded PNG fallback + icon-cache troubleshooting note.
- Still unverified: real Windows GUI, 2-PC LAN test, 2-PC signaling
  test against a deployed server, installer install/uninstall,
  in-app download vs real Release, File Transfer Send still not wired,
  2FA still not implemented (UI says so).

## v1.0.6 addendum (2026-10-14) — INSTALLER UPGRADE FIX ONLY
- User's v1.0.5 screenshots showed the installer failing with
  "Setup was unable to automatically close all applications" and
  "DeleteFile failed; code 5. Access is denied." on
  `...\\Programs\\RemoteDesk\\RemoteDesk.exe` — because the OLD
  RemoteDesk.exe was still RUNNING and locked its own file.
  Consequence: the new EXE never replaced the old one, so the user
  kept seeing the OLD UI and reported "UI change nahi hua".
- Fix (setup.iss [Setup] only): `CloseApplications=yes`,
  `CloseApplicationsFilter=RemoteDesk.exe`,
  `RestartApplications=yes` — the Restart Manager closes the running
  app before files are replaced. No UI redesign in v1.0.6.
- UI VERIFIED in code (grep, v1.0.5 flow already present): single
  "Remote Address" entry (ui.py:625,719) + Enter binding (:629),
  NO pairing-code field anywhere (only a compat no-op at :1583),
  host Accept/Decline popup (:1686/:1689), centered update popup
  with fixed footer (:2286+), Option 1 blue theme (#0B1220 / #2E7DFF).
  Old-UI sightings were failed upgrades, not missing UI code.
- `python3 -m pytest -q` → **79 passed** (unchanged). `python3 run.py
  --version` → `1.0.6`; `setup.iss` MyAppVersion `1.0.6`. Xvfb smoke:
  app builds, pages switch, no exceptions.
- Still unverified: real Windows upgrade run (old app running +
  installer auto-close), 2-PC LAN/signaling test, in-app download
  vs real Release, File Transfer Send still not wired, 2FA still
  not implemented (UI says so). Ship only v1.0.6+.
