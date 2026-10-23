"""Unit tests for the DjangoRateLimitMiddleware integration."""

from typing import Any

import pytest

from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, FilterRule, RateLimitRule
from rate_limiter.limiter import RateLimiter
from rate_limiter.middleware.django import DjangoRateLimitMiddleware


class MockDjangoRequest:
    """Mock simulating a Django WSGI/ASGI HttpRequest."""

    def __init__(
        self,
        path: str = "/django/test",
        meta: dict[str, str] | None = None,
    ) -> None:
        self.path = path
        self.META = meta or {"REMOTE_ADDR": "127.0.0.1"}


class MockDjangoResponse:
    """Mock simulating a Django HttpResponse."""

    def __init__(self, content: str = "ok", status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def __setitem__(self, key: str, value: str) -> None:
        self.headers[key] = value

    def __getitem__(self, key: str) -> str:
        return self.headers[key]


@pytest.mark.asyncio
async def test_django_middleware_async_flow() -> None:
    """Test asynchronous Django view pipeline handling."""
    backend = InMemoryBackend()
    limiter = RateLimiter(
        backend=backend,
        default_rule=RateLimitRule(limit=2, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW),
    )

    async def async_view(req: Any) -> MockDjangoResponse:
        return MockDjangoResponse("async ok", 200)

    middleware = DjangoRateLimitMiddleware(get_response=async_view, limiter=limiter)
    req = MockDjangoRequest()

    # Request 1: allowed
    res1 = await middleware(req)
    assert res1.status_code == 200
    assert "X-RateLimit-Limit" in res1.headers
    assert res1.headers["X-RateLimit-Remaining"] == "1"

    # Request 2: allowed
    res2 = await middleware(req)
    assert res2.status_code == 200
    assert res2.headers["X-RateLimit-Remaining"] == "0"

    # Request 3: blocked (429)
    res3 = await middleware(req)
    assert res3.status_code == 429
    assert "Retry-After" in res3.headers


def test_django_middleware_sync_flow() -> None:
    """Test synchronous Django view pipeline handling."""
    backend = InMemoryBackend()
    limiter = RateLimiter(
        backend=backend,
        default_rule=RateLimitRule(limit=1, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW),
    )

    def sync_view(req: Any) -> MockDjangoResponse:
        return MockDjangoResponse("sync ok", 200)

    middleware = DjangoRateLimitMiddleware(get_response=sync_view, limiter=limiter)
    req = MockDjangoRequest()

    res1 = middleware(req)
    assert res1.status_code == 200
    assert res1.headers["X-RateLimit-Remaining"] == "0"

    res2 = middleware(req)
    assert res2.status_code == 429


@pytest.mark.asyncio
async def test_django_middleware_blacklist() -> None:
    """Ensure blacklisted requests return 403 in Django."""
    backend = InMemoryBackend()
    filters = FilterRule(blacklisted_ips={"10.0.0.50"})
    limiter = RateLimiter(backend=backend, filter_rule=filters)

    async def async_view(req: Any) -> MockDjangoResponse:
        return MockDjangoResponse()

    middleware = DjangoRateLimitMiddleware(get_response=async_view, limiter=limiter)
    req = MockDjangoRequest(meta={"REMOTE_ADDR": "10.0.0.50"})

    res = await middleware(req)
    assert res.status_code == 403
