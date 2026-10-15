"""v1.0.10: tab switches must NOT rebuild widgets.

Root cause of the old new-tab lag: _show_page() rebuilt trusted /
history / file lists on EVERY switch (disk reads + destroy/recreate of
every row). Now only the shown page refreshes, and only when data
changed. Switching tabs must leave the widget tree untouched.
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


def _widget_count(root):
    count = 0
    stack = list(root.winfo_children())
    while stack:
        w = stack.pop()
        count += 1
        stack.extend(w.winfo_children())
    return count


def test_tab_switch_does_not_recreate_widgets(app):
    pages_before = dict(app.pages)
    count_before = _widget_count(app.root)
    for _ in range(3):
        for name in ("Home", "Remote Control", "Viewer", "File Transfer",
                     "Trusted Devices", "Session History", "Settings"):
            app._show_page(name)
            app.root.update_idletasks()
    # Same page frame objects, same total widget count — nothing rebuilt.
    assert app.pages == pages_before
    assert _widget_count(app.root) == count_before


def test_history_refresh_is_noop_when_unchanged(app):
    tree = app.history_tree
    calls = {"delete": 0, "insert": 0}
    orig_delete, orig_insert = tree.delete, tree.insert

    def delete(*a, **k):
        calls["delete"] += 1
        return orig_delete(*a, **k)

    def insert(*a, **k):
        calls["insert"] += 1
        return orig_insert(*a, **k)

    tree.delete, tree.insert = delete, insert
    try:
        app._refresh_history()  # first call after startup cache: may rebuild once
        calls["delete"] = calls["insert"] = 0
        app._refresh_history()  # identical data → zero teardown/rebuild
        assert calls == {"delete": 0, "insert": 0}
    finally:
        tree.delete, tree.insert = orig_delete, orig_insert


def test_ctk_list_batches_bulk_refresh(app):
    lst = ui_module._CTkList(app.root, height=80)
    # Count CTkButton.configure calls during the batch: each insert must
    # configure its own row once (command), and the per-row full refresh
    # (2 configures per row, O(n^2)) must NOT run until end_batch.
    calls = []
    orig_configure = ctk.CTkButton.configure

    def counting(self, *a, **k):
        calls.append(1)
        return orig_configure(self, *a, **k)

    ctk.CTkButton.configure = counting
    try:
        lst.begin_batch()
        for i in range(5):
            lst.insert("end", f"row {i}")
        assert len(calls) == 5, (
            f"batched inserts must configure 5 rows once each, got {len(calls)}")
        lst.end_batch()
        # _refresh is ONE configure call per row (fg_color + text_color).
        assert len(calls) == 5 + 5, (
            "end_batch must run exactly one full refresh (1 call/row)")
    finally:
        ctk.CTkButton.configure = orig_configure
        lst.destroy()
