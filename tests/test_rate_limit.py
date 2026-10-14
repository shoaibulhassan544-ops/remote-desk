"""Rate limiter tests (auth brute-force protection)."""

from app.security import RateLimiter


def test_allows_up_to_max():
    rl = RateLimiter(max_attempts=3, window_s=60, now=lambda: 0.0)
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is True
    assert rl.allow("1.2.3.4") is False


def test_keys_are_independent():
    rl = RateLimiter(max_attempts=1, window_s=60, now=lambda: 0.0)
    assert rl.allow("a") is True
    assert rl.allow("b") is True
    assert rl.allow("a") is False


def test_window_expiry_resets():
    now = [0.0]
    rl = RateLimiter(max_attempts=1, window_s=60, now=lambda: now[0])
    assert rl.allow("a") is True
    assert rl.allow("a") is False
    now[0] = 61.0
    assert rl.allow("a") is True
