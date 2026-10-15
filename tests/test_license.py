"""v1.0.9: the installer must show a license agreement (EULA).

- LICENSE.txt exists in the repo root and is a real EULA (authorized
  use only, no unauthorized access, as-is / no warranty, liability).
- setup.iss wires it in via LicenseFile=LICENSE.txt so Inno Setup shows
  the license page before installing.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_license_file_exists_and_is_real_eula():
    path = os.path.join(ROOT, "LICENSE.txt")
    assert os.path.exists(path), "LICENSE.txt missing from repo root"
    text = open(path, encoding="utf-8").read()
    assert len(text.strip()) > 500
    assert "RemoteDesk" in text
    assert "Authorized" in text or "AUTHORIZED" in text
    assert "consent" in text.lower()
    assert "AS IS" in text
    assert "WARRANTY" in text or "warranty" in text.lower()
    assert "Shoaib Azeez" in text


def test_setup_iss_wires_license_file():
    iss = open(os.path.join(ROOT, "setup.iss"), encoding="utf-8").read()
    assert "LicenseFile=LICENSE.txt" in iss
    # LicenseFile belongs in the [Setup] section, not elsewhere.
    setup_section = iss[iss.index("[Setup]"):iss.index("[Languages]")]
    assert "LicenseFile=LICENSE.txt" in setup_section
