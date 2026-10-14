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

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
