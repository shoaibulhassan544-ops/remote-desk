"""Optional clipboard sync — guarded import, user-controlled, off by default.

Clipboard text is only exchanged while a session is active AND the user
enabled clipboard sync in Settings. Never syncs clipboard outside a session.
"""

try:
    import pyperclip  # type: ignore
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    pyperclip = None  # type: ignore
    _AVAILABLE = False


def clipboard_available() -> bool:
    return _AVAILABLE


def get_text() -> str | None:
    if not _AVAILABLE:
        return None
    try:
        return pyperclip.paste()
    except Exception:
        return None


def set_text(text: str) -> bool:
    if not _AVAILABLE or not isinstance(text, str):
        return False
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False
