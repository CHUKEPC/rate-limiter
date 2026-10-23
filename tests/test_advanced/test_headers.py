"""Tests for HTTP rate limit headers formatting."""

from rate_limiter.config import RateLimitResult
from rate_limiter.headers import build_rate_limit_headers


def test_build_rate_limit_headers_allowed() -> None:
    """Format headers for allowed request."""
    result = RateLimitResult.create(
        allowed=True,
        limit=100,
        remaining=95,
        reset_after=30.4,
        key="test:ip",
        algorithm="sliding_window_counter",
    )
    headers = build_rate_limit_headers(result, current_time=1000.0)
    assert headers["X-RateLimit-Limit"] == "100"
    assert headers["X-RateLimit-Remaining"] == "95"
    assert headers["X-RateLimit-Reset"] == "1030"
    assert "Retry-After" not in headers


def test_build_rate_limit_headers_denied_with_ietf() -> None:
    """Format headers for rejected request with IETF draft headers."""
    result = RateLimitResult.create(
        allowed=False,
        limit=50,
        remaining=0,
        reset_after=12.2,
        key="test:user",
        algorithm="token_bucket",
    )
    headers = build_rate_limit_headers(
        result,
        include_retry_after=True,
        current_time=2000.0,
        use_ietf_standard=True,
    )
    assert headers["X-RateLimit-Limit"] == "50"
    assert headers["X-RateLimit-Remaining"] == "0"
    assert headers["X-RateLimit-Reset"] == "2012"
    assert headers["Retry-After"] == "13"
    assert headers["RateLimit-Limit"] == "50"
    assert headers["RateLimit-Remaining"] == "0"
    assert headers["RateLimit-Reset"] == "12"
