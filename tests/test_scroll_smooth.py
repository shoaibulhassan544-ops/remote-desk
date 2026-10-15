"""v1.0.10: scrolling must move in exactly one step per wheel event,
with no widget rebuild.

The old scratchy feel came from per-switch list rebuilds + redundant
reconfigures firing alongside scroll redraws. Our code must not add its
own global (bind_all) wheel handlers on top of CTk's — one handler, one
step per notch, no layout churn.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402

from app import ui as ui_module  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_SRC = open(os.path.join(ROOT, "app", "ui.py"), encoding="utf-8").read()


def test_no_extra_global_wheel_handlers():
    assert "bind_all" not in UI_SRC, \
        "app must not add global bind_all wheel handlers over CTk's own"


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


def _widget_count(root):
    count = 0
    stack = list(root.winfo_children())
    while stack:
        w = stack.pop()
        count += 1
        stack.extend(w.winfo_children())
    return count


def test_scroll_moves_one_equal_step_per_event_and_no_rebuild(app):
    app._show_page("Home")
    # Map the window at real size: a withdrawn window never gets real
    # geometry, so canvas metrics (and scroll steps) would be meaningless.
    app.root.geometry("1000x680")
    app.root.deiconify()
    app.root.update()
    # CTkScrollableFrame's real object lives inside a canvas window, so it
    # is not reachable via winfo_children — the app keeps a direct handle.
    scroll = app.home_scroll
    assert isinstance(scroll, ctk.CTkScrollableFrame)
    canvas = scroll._parent_canvas
    assert canvas.yview() != (0.0, 1.0), "Home must actually be scrollable"
    before = _widget_count(app.root)
    positions = [canvas.yview()[0]]
    for _ in range(3):
        # Linux wheel: Button-5 = wheel down (scroll content upward).
        # NOTE: update() (not update_idletasks()) — wheel events sit in
        # the event queue and only update() processes them.
        # NOTE: Button-4 (wheel up) at the top cannot move anything, so
        # the test must scroll DOWN from the top.
        canvas.event_generate("<Button-5>")
        app.root.update()
        positions.append(canvas.yview()[0])
    steps = [round(b - a, 6) for a, b in zip(positions, positions[1:])]
    assert all(s > 0 for s in steps), f"each notch must move the view: {steps}"
    assert len(set(steps)) == 1, f"steps must be equal per notch: {steps}"
    assert _widget_count(app.root) == before, \
        "scrolling must not create/destroy widgets"
