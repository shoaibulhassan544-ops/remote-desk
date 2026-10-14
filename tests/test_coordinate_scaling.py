"""Bug B (v1.0.7): viewer sent RAW canvas x,y as absolute host coords,
so clicks landed in the wrong place whenever canvas size != host screen.

scale_coords() maps canvas -> host coords and clamps to host bounds.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ui import scale_coords  # noqa: E402


def test_scales_down_to_host():
    # 1000x600 canvas, 1920x1080 host: centre maps to host centre.
    assert scale_coords(500, 300, 1000, 600, 1920, 1080) == (960, 540)


def test_scales_up_to_host():
    # Small canvas showing a big screen: (100, 100) of 400x300 -> (480, 360).
    assert scale_coords(100, 100, 400, 300, 1920, 1080) == (480, 360)


def test_clamps_to_host_bounds():
    assert scale_coords(9999, -50, 1000, 600, 1920, 1080) == (1919, 0)
    assert scale_coords(0, 0, 1000, 600, 1920, 1080) == (0, 0)


def test_unknown_host_size_falls_back_to_raw():
    assert scale_coords(123, 456, 1000, 600, 0, 0) == (123, 456)
    assert scale_coords(123, 456, 0, 0, 1920, 1080) == (123, 456)


def test_non_square_aspect():
    # 800x600 canvas -> 2560x1440 host.
    assert scale_coords(400, 300, 800, 600, 2560, 1440) == (1280, 720)
