"""Installer guards (v1.0.6 + v1.0.7).

v1.0.6: CloseApplications / RestartApplications so an upgrade never
hits "DeleteFile failed; code 5. Access is denied." because the old
EXE was still running.

v1.0.7 (two fixes):
1) DESKTOP ICON: the shortcut pointed at {app}\\RemoteDesk.exe, so a
   silently missing embedded EXE icon meant a generic default desktop
   icon. Now setup.iss ships assets\\icon.ico as a file AND both
   shortcuts use IconFilename="{app}\\icon.ico" directly.
2) INSTALL WHILE RUNNING: Restart Manager can still pop the "unable
   to close" dialog, so [Code] force-closes RemoteDesk.exe with
   taskkill /F before files are replaced (errors ignored).
"""

import os
import re
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iss() -> str:
    with open(os.path.join(ROOT, "setup.iss"), encoding="utf-8") as f:
        return f.read()


def test_icon_ico_shipped_as_file():
    iss = _iss()
    assert re.search(
        r'Source:\s*"assets\\icon\.ico";\s*DestDir:\s*"\{app\}"',
        iss), "setup.iss must ship assets\\icon.ico into {app}"


def test_both_shortcuts_use_icon_filename():
    iss = _iss()
    icons = iss[iss.index("[Icons]"):]
    icons = icons[:icons.index("[Run]")]
    # Both the Start Menu entry AND the desktop entry.
    assert icons.count('IconFilename: "{app}\\icon.ico"') >= 2, \
        "Start Menu + desktop shortcuts must both set IconFilename to {app}\\icon.ico"


def test_taskkill_force_close_in_code_section():
    iss = _iss()
    code = iss[iss.index("[Code]"):]
    assert "CurStepChanged" in code
    assert "ssInstall" in code
    assert "taskkill.exe" in code
    assert "/F /IM RemoteDesk.exe" in code
    assert "SW_HIDE" in code  # silent: no window, no prompt
    assert "ewWaitUntilTerminated" in code


def test_close_applications_still_present():
    """Belt + suspenders: Restart Manager lines stay alongside taskkill."""
    iss = _iss()
    assert "CloseApplications=yes" in iss
    assert "CloseApplicationsFilter=RemoteDesk.exe" in iss
    assert "RestartApplications=yes" in iss


def test_icon_ico_has_all_six_sizes():
    """16, 24, 32, 48, 64, 256 must all be present (the 24x24 entry was
    missing before v1.0.7). Extra sizes (e.g. 128) are allowed."""
    data = open(os.path.join(ROOT, "assets", "icon.ico"), "rb").read()
    _reserved, _typ, count = struct.unpack("<HHH", data[:6])
    sizes = set()
    for i in range(count):
        w, h, *_rest = struct.unpack("<BBBBHHII", data[6 + i * 16:6 + (i + 1) * 16])
        sizes.add((w or 256, h or 256))
    required = {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)}
    assert required <= sizes, f"icon.ico missing sizes: {sorted(required - sizes)} (has {sorted(sizes)})"


def test_build_workflow_verifies_exe_icon():
    """CI must FAIL the build if the EXE has no icon resources."""
    yml = open(os.path.join(ROOT, ".github", "workflows", "build.yml"),
               encoding="utf-8").read()
    assert "Verify EXE icon" in yml
    assert "pefile" in yml
    # RT_GROUP_ICON = 14, RT_ICON = 3.
    assert "14" in yml and "3" in yml
    # The verify step must run AFTER PyInstaller built the EXE.
    assert yml.index("pyinstaller remote_desk.spec") < yml.index("Verify EXE icon")


def test_version_still_1_0_9():
    assert '"1.0.12"' in _iss()


def test_installer_adds_windows_firewall_rule():
    """v1.0.11: the installer adds a Windows Firewall Allow rule for the
    installed EXE (best-effort: runhidden + unchecked, never fails install)."""
    iss = _iss()
    run = iss[iss.index("[Run]"):]
    assert "netsh" in run
    assert "advfirewall firewall add rule" in run
    assert "RemoteDesk" in run
    assert "runhidden" in run


def test_license_file_present():
    """v1.0.9: the installer shows the EULA (LICENSE.txt) before install."""
    iss = _iss()
    assert "LicenseFile=LICENSE.txt" in iss
    lic = open(os.path.join(ROOT, "LICENSE.txt"), encoding="utf-8").read()
    assert len(lic.strip()) > 500, "LICENSE.txt must be a real EULA, not a stub"
    assert "Authorized" in lic or "authorized" in lic
    assert "AS IS" in lic


def test_install_location_unchanged_since_v105():
    """v1.0.9 in-place upgrade: the install folder + privilege level must
    NEVER change between versions, or upgrades land in a second copy
    and the user is forced into an uninstall-first dance."""
    iss = _iss()
    assert r"DefaultDirName={autopf}\{#MyAppName}" in iss
    assert "PrivilegesRequired=lowest" in iss
