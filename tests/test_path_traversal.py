"""Path-traversal rejection tests (file transfer security)."""

import pytest

from app.security import is_safe_relative_path, safe_join


def test_safe_paths_ok():
    assert is_safe_relative_path("photo.png")[0] is True
    assert is_safe_relative_path("sub/folder/doc.pdf")[0] is True


def test_dotdot_rejected():
    assert is_safe_relative_path("../secret.txt")[0] is False
    assert is_safe_relative_path("a/../../etc/passwd")[0] is False
    assert is_safe_relative_path("..\\windows\\x")[0] is False


def test_absolute_paths_rejected():
    assert is_safe_relative_path("/etc/passwd")[0] is False
    assert is_safe_relative_path("C:\\Windows\\x")[0] is False
    assert is_safe_relative_path("C:/Windows/x")[0] is False


def test_empty_rejected():
    assert is_safe_relative_path("")[0] is False


def test_safe_join_keeps_inside_base(tmp_path):
    out = safe_join(str(tmp_path), "a/b.txt")
    assert out.startswith(str(tmp_path))


def test_safe_join_rejects_escape(tmp_path):
    with pytest.raises(ValueError):
        safe_join(str(tmp_path), "../escape.txt")
