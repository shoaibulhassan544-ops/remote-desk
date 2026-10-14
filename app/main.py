"""RemoteDesk entry point.

Usage:
    python -m app.main            # launch the GUI
    python -m app.main --version  # print version
    python -m app.main --check-update  # one-shot update check (no GUI)
"""

import argparse
import sys

from .version import VERSION


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="RemoteDesk")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--check-update", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(VERSION)
        return 0
    if args.check_update:
        from . import update_checker
        release = update_checker.check_for_update()
        if release:
            print(f"Update available: {release['tag']} — {release['url']}")
        else:
            print("No update available (or update checks not configured).")
        return 0
    from .ui import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
