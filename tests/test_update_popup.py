"""Tests for the v1.0.5 centered update popup helpers + icon assets.

- format_update_status(): MB / % / speed math for the fixed footer.
- ICO must contain all 6 sizes (16/32/48/64/128/256) so Windows shows
  the logo on taskbar + desktop instead of the default icon.
- setup.iss desktop icon task must NOT be unchecked (default ON).
- Embedded icon data must decode to a valid PNG.
"""

import base64
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from app.icon_data import ICON_PNG_B64  # noqa: E402
from app.ui import format_update_status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_format_update_status_with_total():
    s = format_update_status(5 * 1024 * 1024, 20 * 1024 * 1024, 5.0)
    assert "5.0 / 20.0 MB" in s
    assert "(25%)" in s
    assert "1.0 MB/s" in s


def test_format_update_status_no_total():
    s = format_update_status(2 * 1024 * 1024, 0, 2.0)
    assert "2.0 MB" in s
    assert "1.0 MB/s" in s


def test_format_update_status_zero_elapsed_no_crash():
    s = format_update_status(0, 10 * 1024 * 1024, 0.0)
    assert "0.0 / 10.0 MB" in s
    assert "(0%)" in s


def test_ico_contains_all_sizes():
    im = Image.open(os.path.join(ROOT, "assets", "icon.ico"))
    sizes = im.info.get("sizes", set())
    for want in {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}:
        assert want in sizes, f"missing ICO size {want}: {sizes}"


def test_setup_iss_desktop_icon_checked_by_default():
    text = open(os.path.join(ROOT, "setup.iss"), encoding="utf-8").read()
    for line in text.splitlines():
        if 'Name: "desktopicon"' in line:
            assert "unchecked" not in line, "desktop icon must default ON"
            assert "checked" in line
            return
    raise AssertionError("desktopicon task not found in setup.iss")


def test_embedded_icon_decodes_to_png():
    raw = base64.b64decode(ICON_PNG_B64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    im = Image.open(io.BytesIO(raw))
    assert im.size[0] >= 256
