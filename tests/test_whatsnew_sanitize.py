"""v1.0.9: "What's new" showed a bare GitHub compare link
("**Full Changelog**: https://github.com/.../compare/v1.0.7...v1.0.8").

GitHub auto-appends that compare line to release notes. sanitize_notes()
drops it (and any other github.com line), strips markdown-link syntax to
plain text, and the fallback chain (sanitized body -> built-in CHANGELOG
-> generic line) means the box is never blank AND never shows a GitHub URL.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.update_checker import resolve_notes, sanitize_notes  # noqa: E402

COMPARE_NOTES = (
    "• Real fix one.\n"
    "• Real fix two.\n"
    "\n"
    "**Full Changelog**: https://github.com/shoaibulhassan544-ops/remote-desk/compare/v1.0.7...v1.0.8\n"
)


def test_compare_line_removed_but_real_notes_kept():
    out = sanitize_notes(COMPARE_NOTES)
    assert "Real fix one." in out
    assert "Real fix two." in out
    assert "github.com" not in out
    assert "compare/" not in out
    assert "Full Changelog" not in out


def test_compare_only_notes_sanitize_to_empty():
    out = sanitize_notes(
        "**Full Changelog**: https://github.com/x/y/compare/v1.0.7...v1.0.8\n")
    assert out == ""


def test_compare_only_notes_fall_back_to_builtin_changelog():
    notes = resolve_notes(
        "v1.0.9",
        "**Full Changelog**: https://github.com/shoaibulhassan544-ops/remote-desk/compare/v1.0.7...v1.0.8\n")
    # Body had only the compare line -> falls back to the built-in entry.
    assert "AUTO-INSTALL" in notes
    assert "github.com" not in notes


def test_markdown_links_stripped_to_text():
    out = sanitize_notes("See [the guide](https://example.com/guide) for details.")
    assert out == "See the guide for details."
    assert "https://" not in out


def test_plain_notes_kept_verbatim():
    out = sanitize_notes("Custom release notes here.")
    assert out == "Custom release notes here."


def test_bare_github_url_line_dropped():
    out = sanitize_notes("Notes here.\nhttps://github.com/x/y/releases/tag/v1.0.9\nMore here.")
    assert "github.com" not in out
    assert "Notes here." in out
    assert "More here." in out


def test_empty_after_sanitize_falls_back_to_generic():
    notes = resolve_notes("v9.9.9", "**Full Changelog**: https://github.com/x/y/compare/a...b")
    assert notes.strip()
    assert "github.com" not in notes


def test_changelog_has_v109_entry():
    notes = resolve_notes("v1.0.9", "")
    assert "AUTO-INSTALL" in notes
    assert "github.com" not in notes
