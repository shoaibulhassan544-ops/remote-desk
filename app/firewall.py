"""Windows Firewall helper (v1.0.11).

Windows Defender Firewall silently drops inbound TCP (host port) + inbound
UDP (discovery) on first run when no rule exists — the most likely cause
of "IP connect bhi fail" on a fresh install. Nothing in the app ever
added a firewall exception before v1.0.11.

- The installer adds the rule best-effort via netsh (see setup.iss [Run]).
- This module lets the user add it from Settings → Network, with an
  elevation prompt (UAC) when admin rights are needed.
- Pure helpers (command building) are fully testable; the
  subprocess/ctypes runners are injectable.
"""

import subprocess
import sys

RULE_NAME = "RemoteDesk"


def firewall_rule_command(exe_path: str) -> list[str]:
    """netsh argv that allows inbound traffic for the RemoteDesk EXE."""
    return [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={RULE_NAME}", "dir=in", "action=allow",
        f'program="{exe_path}"', "enable=yes",
    ]


def add_firewall_rule(exe_path: str, runner=None) -> tuple[bool, str]:
    """Try to add the rule WITHOUT elevation. Returns (ok, message).

    On a standard (non-admin) account this fails — the caller should
    then offer the elevated path. Never raises.
    """
    run = runner or subprocess.run
    try:
        result = run(firewall_rule_command(exe_path),
                     capture_output=True, text=True, timeout=30)
    except (OSError, ValueError) as exc:
        return False, f"Firewall rule add nahi hui: {exc}"
    except Exception as exc:  # noqa: BLE001 — never crash the UI
        return False, f"Firewall rule add nahi hui: {exc}"
    if getattr(result, "returncode", 1) == 0:
        return True, "Windows Firewall me RemoteDesk Allow ho gaya ✓"
    err = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "").strip()
    return False, f"Firewall rule add nahi hui (admin chahiye): {err}"


def add_firewall_rule_elevated(exe_path: str, shell_exec=None) -> tuple[bool, str]:
    """Re-run netsh with a UAC elevation prompt (Windows only).

    Uses ShellExecuteW "runas" — Windows shows the standard "Allow this
    app to make changes?" prompt. Returns (True, ...) when the prompt
    was shown; the actual rule result is reported by the follow-up
    non-elevated check / next connect attempt. Never raises.
    """
    if sys.platform != "win32":
        return False, "Firewall rule sirf Windows pe lagti hai."
    try:
        if shell_exec is not None:
            code = shell_exec("runas", "netsh", _elevated_params(exe_path))
        else:
            import ctypes
            code = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "netsh", _elevated_params(exe_path), None, 0)
        # ShellExecuteW returns > 32 on success (prompt shown / started).
        if isinstance(code, int) and code > 32:
            return True, ("Admin prompt dikhaya gaya — usme Yes dabao, "
                           "phir dobara Connect try karo.")
        return False, "Admin prompt nahi khula — dobara try karo."
    except Exception as exc:  # noqa: BLE001 — never crash the UI
        return False, f"Admin prompt nahi khula: {exc}"


def _elevated_params(exe_path: str) -> str:
    parts = firewall_rule_command(exe_path)[1:]  # drop "netsh"
    return " ".join(parts)
