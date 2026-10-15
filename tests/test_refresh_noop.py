"""v1.0.10: refresh helpers must be no-ops when nothing changed.

Calling a refresh twice with identical state must perform zero widget
reconfigures — the old code reconfigured labels / pills / nav buttons on
every call, which added redraw churn on every tab switch and pump tick.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402

from app import ui as ui_module  # noqa: E402


@pytest.fixture()
def app():
    try:
        root = ctk.CTk()
    except Exception as exc:  # no display (plain pytest, no Xvfb)
        pytest.skip(f"no display for live-Tk test: {exc}")
    root.withdraw()
    instance = ui_module.RemoteDeskApp(root)
    root.update_idletasks()
    yield instance
    try:
        root.destroy()
    except Exception:
        pass


def _counting(widget, method_name="configure"):
    calls = []

    orig = getattr(widget, method_name)

    def wrapper(*a, **k):
        calls.append(1)
        return orig(*a, **k)

    setattr(widget, method_name, wrapper)
    return calls


def test_refresh_pill_noop_on_unchanged_state(app):
    calls = _counting(app.status_pill)
    app._refresh_pill()
    app._refresh_pill()
    assert calls == [], "pill must not reconfigure when state is unchanged"


def test_refresh_nav_noop_on_same_page(app):
    app._show_page("Home")
    app.root.update_idletasks()
    all_calls = []
    for btn in app._nav_btns.values():
        all_calls.append(_counting(btn))
    app._refresh_nav()
    app._refresh_nav()
    assert sum(len(c) for c in all_calls) == 0, \
        "nav buttons must not reconfigure when the page is unchanged"


def test_refresh_home_history_noop_on_unchanged_data(app):
    calls = _counting(app.home_history_box)
    app._refresh_home_history()
    app._refresh_home_history()
    assert calls == [], "home history box must not rewrite identical text"


def test_refresh_file_dest_noop_on_unchanged_values(app):
    calls = _counting(app.ft_dest)
    app._refresh_file_dest()  # prime the cache (first call does real work)
    assert len(calls) == 1
    del calls[:]
    app._refresh_file_dest()
    app._refresh_file_dest()
    assert calls == [], "file-dest combo must not reconfigure identical values"
