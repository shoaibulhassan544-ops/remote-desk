"""v1.0.10: CI Windows smoke test + DLL-load hardening.

The user hit "Failed to load Python DLL ... python311.dll" on the
portable EXE — a build that shipped without ever being STARTED on
Windows. From v1.0.10 the GitHub Windows runner must smoke-test the
built EXE AND the installed EXE (--version, exit 0) before any
release asset ships. UPX is disabled (known cause of AV interference
+ extraction/DLL load failures) and no VC++ runtime DLLs are
excluded from the bundle.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_YML = open(os.path.join(ROOT, ".github/workflows/build.yml"),
                 encoding="utf-8").read()
SPEC = open(os.path.join(ROOT, "remote_desk.spec"), encoding="utf-8").read()
RUN_PY = open(os.path.join(ROOT, "run.py"), encoding="utf-8").read()


def test_build_yml_has_built_exe_smoke_test():
    assert "Smoke-test built EXE" in BUILD_YML
    assert "dist\\RemoteDesk.exe" in BUILD_YML
    assert '"--version"' in BUILD_YML
    assert "WaitForExit(60000)" in BUILD_YML, \
        "smoke test must time out instead of hanging on a DLL-error dialog"


def test_build_yml_has_installed_exe_smoke_test():
    assert "Smoke-test installed EXE" in BUILD_YML
    assert "/VERYSILENT" in BUILD_YML
    assert "/SUPPRESSMSGBOXES" in BUILD_YML
    assert "/NORESTART" in BUILD_YML
    assert "/DIR=" in BUILD_YML
    assert 'RemoteDesk.exe" -ArgumentList "--version"' in BUILD_YML \
        or "installed RemoteDesk.exe --version" in BUILD_YML


def test_smoke_tests_run_before_release():
    release_pos = BUILD_YML.find("Create GitHub Release")
    assert release_pos > 0
    assert BUILD_YML.find("Smoke-test built EXE") < release_pos
    assert BUILD_YML.find("Smoke-test installed EXE") < release_pos


def test_upx_disabled_and_no_vc_runtime_exclusions():
    assert "upx=False" in SPEC, "UPX must be disabled (DLL-load failures)"
    assert "upx=True" not in SPEC
    assert "excludes=[]" in SPEC, \
        "excludes must stay empty — no VC++ runtime DLLs excluded"


def test_run_py_handles_version_without_tkinter():
    # --version is handled in run.py BEFORE any app.main import, so it
    # can never pull in Tkinter / open a GUI window.
    early = RUN_PY.split("from app.main import")[0]
    assert "--version" in early
    assert "import tkinter" not in RUN_PY
    assert "from tkinter" not in RUN_PY
    # And the real thing: subprocess --version prints the version, rc 0,
    # with no display needed (proves no GUI code runs).
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "run.py"), "--version"],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    from app.version import VERSION  # noqa: E402

    assert proc.stdout.strip() == VERSION
