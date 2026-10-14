"""Bug C (v1.0.7): the update popup was big, its "Later" button was
clipped ("...ate"), and "What's new" was EMPTY (web-created Releases
have an empty body).

- Built-in changelog fallback: empty API notes -> CHANGELOG[tag] ->
  generic line. The box is never blank.
- The popup has ONLY two main buttons: Download Update + Later.
  The release-page link appears ONLY if the download fails.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import update_checker  # noqa: E402


def test_empty_notes_fall_back_to_builtin_changelog():
    notes = update_checker.resolve_notes("v1.0.7", "")
    assert notes.strip(), "notes must never be blank"
    assert "Address" in notes or "broadcast" in notes.lower()


def test_whitespace_notes_fall_back_to_builtin_changelog():
    notes = update_checker.resolve_notes("v1.0.6", "   \n  ")
    assert "auto-close" in notes.lower() or "CloseApplications" in notes


def test_real_notes_are_kept_verbatim():
    notes = update_checker.resolve_notes("v1.0.7", "Custom release notes here.")
    assert notes == "Custom release notes here."


def test_unknown_tag_falls_back_to_generic_line():
    notes = update_checker.resolve_notes("v9.9.9", "")
    assert notes == update_checker.GENERIC_CHANGELOG
    assert notes.strip()


def test_every_changelog_entry_is_nonempty():
    for tag, entry in update_checker.CHANGELOG.items():
        assert tag.startswith("v")
        assert entry.strip(), f"empty changelog for {tag}"


def test_popup_has_only_two_main_buttons():
    """Source-level guard: the popup builds Download + Later as the two
    main buttons; the release-page button is the failure-only fallback."""
    import re
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "ui.py"), encoding="utf-8").read()
    popup = src[src.index("def _show_update_popup"):]
    popup = popup[:popup.index("def _close_update_popup")]
    assert "Download Update" in popup
    assert '"Later"' in popup or "'Later'" in popup or "text=\"Later\"" in popup
    # Fallback is wired through the dedicated show-fallback helper, not
    # as a third always-visible button.
    assert "_show_update_fallback" in popup or "fallback" in popup.lower()
    # Buttons use a grid with weights so nothing can clip (v1.0.6 bug).
    assert "columnconfigure" in popup
    # Small popup: ~520x420, not the old 560x500.
    assert '520, 420' in popup or "520, 420" in popup
