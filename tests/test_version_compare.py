"""Version comparison tests (update checker)."""

import pytest

from app.update_checker import is_newer, parse_version


def test_parse_version_v_prefix():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2") == (1, 2, 0)


def test_is_newer():
    assert is_newer("v1.0.1", "1.0.0") is True
    assert is_newer("v1.1.0", "1.0.9") is True
    assert is_newer("v2.0.0", "1.9.9") is True


def test_is_not_newer_equal_or_older():
    assert is_newer("v1.0.0", "1.0.0") is False
    assert is_newer("v0.9.9", "1.0.0") is False


def test_parse_garbage_raises():
    with pytest.raises(ValueError):
        parse_version("not-a-version")
    with pytest.raises(ValueError):
        parse_version("")
