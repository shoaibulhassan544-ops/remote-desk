"""RemoteDesk entry point for PyInstaller / direct run.

Why this file exists:
    app/main.py uses relative imports (``from .version import ...``).
    Running ``python app/main.py`` directly treats it as a top-level
    script with no parent package, so Python raises:
    "attempted relative import with no known parent package".
    The correct source run is ``python -m app.main``.

    PyInstaller has the same problem when its entry is app/main.py,
    so the spec uses THIS file instead. It uses absolute imports,
    which loads ``app`` as a real package, so all relative imports
    inside app/ work.
"""

import sys


def _early_version_exit() -> None:
    """Handle --version BEFORE importing app.main at all.

    v1.0.10: the CI smoke test runs the built EXE with --version to
    prove the bundle extracts and the Python DLL loads. That check
    must never touch Tkinter (no GUI window, no display needed) —
    even if app.main ever gains a Tk import at module level. The
    full argparse (--version / --check-update / --help) still lives
    in app.main for the normal path.
    """
    args = sys.argv[1:]
    if "--version" in args or "-V" in args:
        from app.version import VERSION

        print(VERSION)
        raise SystemExit(0)


if __name__ == "__main__":
    _early_version_exit()
    from app.main import main

    sys.exit(main())
