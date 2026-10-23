"""Shared pytest fixtures for the rate limiter test suite."""

from collections.abc import AsyncGenerator
from typing import Any

import fakeredis.aioredis
import pytest
from starlette.requests import Request

from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.backends.redis import RedisBackend
from rate_limiter.config import AlgorithmType, RateLimitRule
from rate_limiter.limiter import RateLimiter


@pytest.fixture
def memory_backend() -> InMemoryBackend:
    """Provide a fresh InMemoryBackend instance."""
    return InMemoryBackend()


@pytest.fixture
async def fake_redis() -> AsyncGenerator[Any, None]:
    """Provide a fresh FakeRedis async client with Lua support."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
async def redis_backend(fake_redis: Any) -> AsyncGenerator[RedisBackend, None]:
    """Provide a RedisBackend connected to the fake Redis client."""
    backend = RedisBackend(redis_client=fake_redis, prefix="test_rl:")
    yield backend
    await backend.close()


@pytest.fixture
def sample_rule() -> RateLimitRule:
    """Standard baseline rate limit rule (5 req / 10s)."""
    return RateLimitRule(
        limit=5,
        period=10.0,
        algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER,
    )


@pytest.fixture
def test_limiter(memory_backend: InMemoryBackend) -> RateLimiter:
    """Standard RateLimiter with in-memory storage."""
    return RateLimiter(backend=memory_backend)


def make_mock_request(
    path: str = "/api/test",
    headers: dict[str, str] | None = None,
    client_host: str | None = "127.0.0.1",
    query_string: str = "",
) -> Request:
    """Helper to construct mock ASGI requests."""
    header_list = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()
    ]
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": header_list,
        "client": (client_host, 12345) if client_host is not None else None,
        "query_string": query_string.encode("utf-8"),
    }
    return Request(scope)
