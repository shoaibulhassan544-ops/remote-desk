"""Remote input (mouse/keyboard) via pynput — guarded import.

Input is applied ONLY when the session explicitly grants control permission
(session.py). The controller itself never decides permission; callers must
check `session.can_control()` before calling apply_event().
On systems without pynput, all methods are safe no-ops returning False.
"""

try:
    from pynput import mouse as _mouse, keyboard as _keyboard  # type: ignore
    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _mouse = _keyboard = None  # type: ignore
    _AVAILABLE = False


def input_available() -> bool:
    return _AVAILABLE


class InputController:
    """Applies validated input events: move/click/scroll/key."""

    def __init__(self):
        self._mouse = _mouse.Controller() if _AVAILABLE else None
        self._keyboard = _keyboard.Controller() if _AVAILABLE else None
        self._buttons = {
            "left": _mouse.Button.left,
            "right": _mouse.Button.right,
            "middle": _mouse.Button.middle,
        } if _AVAILABLE else {}

    def apply_event(self, event: dict) -> bool:
        """event: {"kind": "move"|"click"|"scroll"|"key", ...}. Returns applied?"""
        if not _AVAILABLE or not isinstance(event, dict):
            return False
        kind = event.get("kind")
        try:
            if kind == "move":
                self._mouse.position = (int(event["x"]), int(event["y"]))
                return True
            if kind == "click":
                btn = self._buttons.get(str(event.get("button", "left")))
                if btn is None:
                    return False
                if event.get("pressed"):
                    self._mouse.press(btn)
                else:
                    self._mouse.release(btn)
                return True
            if kind == "scroll":
                self._mouse.scroll(int(event.get("dx", 0)), int(event.get("dy", 0)))
                return True
            if kind == "key":
                key = str(event.get("key", ""))
                if len(key) != 1:
                    return False  # special keys intentionally unsupported in v1
                if event.get("pressed"):
                    self._keyboard.press(key)
                else:
                    self._keyboard.release(key)
                return True
        except (KeyError, TypeError, ValueError):
            return False
        return False
