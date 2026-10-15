"""v1.0.8: the UI is rebuilt on CustomTkinter.

- customtkinter must import; app.ui must expose the same entry points
  (RemoteDeskApp, run) and the same pure helpers (format_update_status,
  scale_coords) the old tests use.
- Theme tokens: dark card must differ from dark bg (real card separation),
  accent must be the AnyDesk Blue #2E7DFF.
- Source guard: no flat tkinter widgets in the new UI — CTk everywhere —
  except the three justified exceptions (tk.Canvas viewer surface,
  ttk.Treeview history table, tkinter file/message dialogs).
- Built-in changelog must carry a v1.0.8 entry so the update popup's
  "What's new" box is never blank for this release.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402

from app import ui as ui_module  # noqa: E402
from app.update_checker import resolve_notes  # noqa: E402
from app.version import VERSION  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_SRC = open(os.path.join(ROOT, "app", "ui.py"), encoding="utf-8").read()


def test_customtkinter_imports():
    assert ctk.CTk is not None
    assert ctk.CTkFrame is not None
    assert ctk.CTkButton is not None
    assert ctk.CTkEntry is not None
    assert ctk.CTkLabel is not None
    assert ctk.CTkSwitch is not None
    assert ctk.CTkComboBox is not None
    assert ctk.CTkProgressBar is not None
    assert ctk.CTkScrollableFrame is not None
    assert ctk.CTkToplevel is not None


def test_ui_entry_points_and_helpers():
    assert callable(ui_module.RemoteDeskApp)
    assert callable(ui_module.run)
    assert callable(ui_module.format_update_status)
    assert callable(ui_module.scale_coords)
    assert VERSION == "1.0.8"


def test_theme_tokens_real_card_separation():
    dark = ui_module.BLUE_DARK
    assert dark["card"] != dark["bg"], "card must visually separate from bg"
    assert dark["accent"] == "#2E7DFF"
    assert dark["accent_hover"] == "#1D6FE0"
    assert dark["card"] == "#16263F"
    assert dark["bg"] == "#0B1220"
    assert dark["sidebar"] == "#0A0F1E"
    assert dark["border"] == "#22365C"
    light = ui_module.BLUE_LIGHT
    assert light["card"] != light["bg"]
    assert light["card"] == "#FFFFFF"


def test_no_flat_tkinter_widgets_except_justified():
    # Flat tkinter widgets must NOT appear in the new UI.
    for pattern in (r"\btk\.Button\(", r"\btk\.Entry\(", r"\btk\.LabelFrame",
                    r"\btkinter\.Button", r"\btkinter\.Entry"):
        assert not re.search(pattern, UI_SRC), f"flat widget still used: {pattern}"
    # CTk widgets must be used throughout.
    for widget in ("CTkFrame", "CTkButton", "CTkEntry", "CTkLabel", "CTkSwitch",
                   "CTkComboBox", "CTkProgressBar", "CTkScrollableFrame",
                   "CTkToplevel", "CTkTextbox", "CTkCheckBox"):
        assert f"ctk.{widget}" in UI_SRC or f"CTk{widget[3:]}" in UI_SRC, \
            f"missing CTk widget: {widget}"
    # Justified exceptions (documented in ui.py header): viewer drawing
    # surface, history table, file/message dialogs.
    assert "tk.Canvas" in UI_SRC
    assert "ttk.Treeview" in UI_SRC
    assert "filedialog" in UI_SRC and "messagebox" in UI_SRC


def test_update_popup_uses_real_update_dict_keys():
    # Regression: check_for_update returns {tag, notes, url, assets} —
    # the UI must not read the old invented keys (latest_version /
    # release_notes / download_url / update_available).
    for bad in ("latest_version", "release_notes", "update_available",
                "download_file", "release_page_url"):
        assert bad not in UI_SRC, f"UI uses non-existent update API key: {bad}"
    assert 'update.get("tag")' in UI_SRC
    assert 'update.get("notes")' in UI_SRC
    assert "select_setup_asset" in UI_SRC
    assert "download_update" in UI_SRC


def test_changelog_has_v108_entry():
    notes = resolve_notes("v1.0.8", "")
    assert "CustomTkinter" in notes
    assert "Accept" in notes
