"""v1.0.9: auto-install after download (user feedback on v1.0.7->v1.0.8).

Old behaviour: download finished -> a manual [Run Installer] button,
while the app stayed OPEN and locked RemoteDesk.exe, so the install
failed. New behaviour: download finishes -> [Install Now] + a
3-second countdown; at 0 (or on Install Now) the installer is launched
DETACHED (it survives our exit) and the app closes itself. [Later]
cancels the auto-install. The installer is NEVER launched while the
app is still running. No real installer is launched in these tests —
everything goes through mocks/fakes.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import update_checker  # noqa: E402
from app import ui as ui_module  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_SRC = open(os.path.join(ROOT, "app", "ui.py"), encoding="utf-8").read()


class FakePopen:
    def __init__(self):
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return "MOCK-PROC"


def test_launch_detached_windows_flags():
    fake = FakePopen()
    proc = update_checker.launch_installer_detached(
        r"C:\x\Setup.exe", platform="win32", popen=fake)
    assert proc == "MOCK-PROC"
    args, kwargs = fake.calls[0]
    assert args == [r"C:\x\Setup.exe"]
    # DETACHED_PROCESS (0x08) + CREATE_NEW_PROCESS_GROUP (0x200).
    assert kwargs["creationflags"] == 0x00000008 | 0x00000200
    assert kwargs["close_fds"] is True


def test_launch_detached_posix_new_session():
    fake = FakePopen()
    update_checker.launch_installer_detached("/tmp/Setup", platform="linux",
                                             popen=fake)
    args, kwargs = fake.calls[0]
    assert args == ["/tmp/Setup"]
    assert kwargs.get("start_new_session") is True
    assert "creationflags" not in kwargs


class _FakeVar:
    def __init__(self):
        self.values = []

    def set(self, value):
        self.values.append(value)


class _FakeDialog:
    def __init__(self):
        self.after_calls = []
        self.destroyed = False

    def winfo_exists(self):
        return not self.destroyed

    def after(self, ms, fn):
        self.after_calls.append((ms, fn))
        return "after-id"

    def destroy(self):
        self.destroyed = True


class _FakeButton:
    def __init__(self):
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)


def _make_app(countdown=3):
    """RemoteDeskApp WITHOUT __init__ (no Tk root): only the popup state."""
    app = ui_module.RemoteDeskApp.__new__(ui_module.RemoteDeskApp)
    dlg = _FakeDialog()
    var = _FakeVar()
    btn = _FakeButton()
    app._update_popup = {
        "dialog": dlg, "status_var": var, "btn_dl": btn,
        "state": {"downloading": False, "done_path": "/tmp/Setup.exe",
                  "auto_install_cancelled": False, "countdown": countdown},
    }
    app._downloaded_path = "/tmp/Setup.exe"
    app._launched = []
    app._exited = []
    # Swap the real launcher/exit for spies.
    app._launch_installer_and_exit = lambda: (
        app._launched.append(True), app._exited.append(True))
    return app, dlg, var, btn


def test_countdown_ticks_down_and_launches_at_zero():
    app, dlg, var, _btn = _make_app(countdown=2)
    app._tick_auto_install()  # 2 -> 1, reschedules
    assert app._update_popup["state"]["countdown"] == 1
    assert not app._launched
    assert len(dlg.after_calls) == 1  # rescheduled for the next tick
    assert "1 seconds" in var.values[-1]
    app._tick_auto_install()  # 1 -> 0, launches + exits
    assert app._launched == [True]
    assert app._exited == [True]


def test_install_now_skips_countdown():
    app, dlg, var, _btn = _make_app(countdown=3)
    app._install_now()
    assert app._launched == [True]
    assert app._exited == [True]


def test_later_cancels_auto_install():
    app, dlg, var, _btn = _make_app(countdown=3)
    app._cancel_auto_install()
    assert app._update_popup["state"]["auto_install_cancelled"] is True
    assert dlg.destroyed is True
    # A tick after Later must NOT launch anything.
    app._tick_auto_install()
    assert app._launched == []


def test_tick_stops_when_dialog_closed():
    app, dlg, var, _btn = _make_app(countdown=3)
    dlg.destroy()
    app._tick_auto_install()
    assert app._launched == []


def test_no_manual_run_installer_button_in_ui():
    """The manual [Run Installer] button is gone from the UI source."""
    assert "Run Installer" not in UI_SRC
    assert "_run_downloaded_installer" not in UI_SRC
    assert "Install Now" in UI_SRC
    assert "launch_installer_detached" in UI_SRC
    assert "_exit_for_install" in UI_SRC
    assert "countdown" in UI_SRC
