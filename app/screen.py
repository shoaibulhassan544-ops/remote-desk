"""Screen capture -> JPEG bytes. Guarded: returns None when unavailable.

Windows: mss + Pillow. On Linux dev machines without a display, or when
mss is not installed, capture_jpeg() returns None and the caller must
show a clear error — never a fake/stale frame.
"""

import io

try:
    import mss  # type: ignore
    from PIL import Image  # type: ignore
    _AVAILABLE = True
    _IMPORT_ERROR = ""
except ImportError as exc:  # pragma: no cover - environment dependent
    mss = None  # type: ignore
    Image = None  # type: ignore
    _AVAILABLE = False
    _IMPORT_ERROR = str(exc)


def capture_available() -> bool:
    return _AVAILABLE


def capture_jpeg(quality: int = 70, max_width: int = 1920) -> bytes | None:
    """Capture the primary monitor and return JPEG bytes, or None."""
    jpeg, _w, _h = capture_jpeg_with_size(quality, max_width)
    return jpeg


def capture_jpeg_with_size(quality: int = 70, max_width: int = 1920) -> tuple[bytes | None, int, int]:
    """Capture the primary monitor. Returns (jpeg_bytes_or_None, width, height).

    Width/height are the size of the captured image AFTER any downscale,
    i.e. the coordinate space the guest must map its clicks into.
    Returns (None, 0, 0) when capture is unavailable.
    """
    if not _AVAILABLE:
        return None, 0, 0
    quality = max(10, min(95, int(quality)))
    try:
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    except Exception:
        return None, 0, 0
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), img.width, img.height


def screen_size() -> tuple[int, int]:
    """Primary monitor size in pixels, or (0, 0) when unavailable."""
    if not _AVAILABLE:
        return 0, 0
    try:
        with mss.mss() as sct:
            mon = sct.monitors[1]
            return int(mon["width"]), int(mon["height"])
    except Exception:
        return 0, 0
