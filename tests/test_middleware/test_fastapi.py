"""Integration tests for FastAPI / Starlette RateLimitMiddleware."""

import httpx
import pytest
from fastapi import FastAPI

from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, FilterRule, RateLimitRule
from rate_limiter.limiter import RateLimiter
from rate_limiter.middleware.fastapi import RateLimitMiddleware


@pytest.fixture
def test_app() -> FastAPI:
    """Construct a FastAPI testing application with middleware and sample routes."""
    backend = InMemoryBackend()
    filters = FilterRule(
        whitelisted_paths={"/whitelist"},
        blacklisted_ips={"192.0.2.99"},
    )
    limiter = RateLimiter(
        backend=backend,
        default_rule=RateLimitRule(limit=3, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW),
        filter_rule=filters,
    )

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limiter=limiter, include_headers=True)

    @app.get("/test")
    async def sample_endpoint() -> dict[str, str]:
        return {"message": "hello"}

    @app.get("/whitelist")
    async def whitelisted_endpoint() -> dict[str, str]:
        return {"message": "unlimited"}

    return app


@pytest.mark.asyncio
async def test_fastapi_middleware_allowed_and_headers(test_app: FastAPI) -> None:
    """Verify rate limit headers on successful requests."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        res = await client.get("/test")
        assert res.status_code == 200
        assert res.json() == {"message": "hello"}

        # Inspect headers
        assert "x-ratelimit-limit" in res.headers
        assert res.headers["x-ratelimit-limit"] == "3"
        assert "x-ratelimit-remaining" in res.headers
        assert res.headers["x-ratelimit-remaining"] == "2"
        assert "x-ratelimit-reset" in res.headers


@pytest.mark.asyncio
async def test_fastapi_middleware_429_exceeded(test_app: FastAPI) -> None:
    """Verify HTTP 429 Too Many Requests response upon exceeding quota."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 3 allowed requests
        for _ in range(3):
            r = await client.get("/test")
            assert r.status_code == 200

        # 4th request must be blocked with 429
        blocked = await client.get("/test")
        assert blocked.status_code == 429
        assert "retry-after" in blocked.headers
        data = blocked.json()
        assert data["error"] == "Rate limit exceeded"
        assert data["remaining"] == 0
        assert data["limit"] == 3


@pytest.mark.asyncio
async def test_fastapi_middleware_whitelist(test_app: FastAPI) -> None:
    """Ensure whitelisted paths bypass rate limits without being throttled."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        for _ in range(10):
            res = await client.get("/whitelist")
            assert res.status_code == 200


@pytest.mark.asyncio
async def test_fastapi_middleware_blacklist(test_app: FastAPI) -> None:
    """Ensure blacklisted clients are rejected with HTTP 403 Forbidden."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        res = await client.get("/test", headers={"x-forwarded-for": "192.0.2.99"})
        assert res.status_code == 403
        data = res.json()
        assert data["error"] == "Forbidden"
