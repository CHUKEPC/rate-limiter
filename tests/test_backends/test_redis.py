"""Integration tests for the RedisBackend using FakeRedis and Lua scripts."""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from rate_limiter.backends.redis import RedisBackend
from rate_limiter.config import AlgorithmType, RateLimitRule
from rate_limiter.exceptions import BackendError


@pytest.mark.asyncio
async def test_redis_fixed_window(redis_backend: RedisBackend) -> None:
    """Test distributed Fixed Window counter on Redis."""
    rule = RateLimitRule(limit=3, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
    key = "redis:fw:1"
    t0 = 1000.0

    r1 = await redis_backend.acquire(key, rule, cost=1, current_time=t0)
    assert r1.allowed is True
    assert r1.remaining == 2

    r2 = await redis_backend.acquire(key, rule, cost=2, current_time=t0 + 1.0)
    assert r2.allowed is True
    assert r2.remaining == 0

    r3 = await redis_backend.acquire(key, rule, cost=1, current_time=t0 + 2.0)
    assert r3.allowed is False
    assert r3.remaining == 0


@pytest.mark.asyncio
async def test_redis_sliding_window_log(redis_backend: RedisBackend) -> None:
    """Test distributed Sliding Window Log on Redis ZSET."""
    rule = RateLimitRule(limit=2, period=5.0, algorithm=AlgorithmType.SLIDING_WINDOW_LOG)
    key = "redis:swl:1"

    r1 = await redis_backend.acquire(key, rule, cost=1, current_time=10.0)
    assert r1.allowed is True
    assert r1.remaining == 1

    r2 = await redis_backend.acquire(key, rule, cost=1, current_time=11.0)
    assert r2.allowed is True
    assert r2.remaining == 0

    r3 = await redis_backend.acquire(key, rule, cost=1, current_time=12.0)
    assert r3.allowed is False

    # Eviction past period: at t=15.1, t=10.0 is evicted
    r4 = await redis_backend.acquire(key, rule, cost=1, current_time=15.1)
    assert r4.allowed is True


@pytest.mark.asyncio
async def test_redis_sliding_window_counter(redis_backend: RedisBackend) -> None:
    """Test distributed Sliding Window Counter on Redis."""
    rule = RateLimitRule(limit=4, period=10.0, algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER)
    key = "redis:swc:1"

    r1 = await redis_backend.acquire(key, rule, cost=2, current_time=100.0)
    assert r1.allowed is True
    assert r1.remaining == 2

    r2 = await redis_backend.acquire(key, rule, cost=2, current_time=101.0)
    assert r2.allowed is True
    assert r2.remaining == 0

    r3 = await redis_backend.acquire(key, rule, cost=1, current_time=102.0)
    assert r3.allowed is False


@pytest.mark.asyncio
async def test_redis_token_bucket(redis_backend: RedisBackend) -> None:
    """Test distributed Token Bucket on Redis."""
    rule = RateLimitRule(
        limit=5,
        period=5.0,
        burst=10,
        algorithm=AlgorithmType.TOKEN_BUCKET,
    )
    key = "redis:tb:1"

    r1 = await redis_backend.acquire(key, rule, cost=10, current_time=200.0)
    assert r1.allowed is True
    assert r1.remaining == 0

    # Bucket empty
    r2 = await redis_backend.acquire(key, rule, cost=1, current_time=200.0)
    assert r2.allowed is False

    # Refill 2 tokens after 2 seconds
    r3 = await redis_backend.acquire(key, rule, cost=2, current_time=202.0)
    assert r3.allowed is True


@pytest.mark.asyncio
async def test_redis_leaky_bucket(redis_backend: RedisBackend) -> None:
    """Test distributed Leaky Bucket on Redis."""
    rule = RateLimitRule(
        limit=5,
        period=5.0,
        burst=5,
        algorithm=AlgorithmType.LEAKY_BUCKET,
    )
    key = "redis:lb:1"

    r1 = await redis_backend.acquire(key, rule, cost=5, current_time=300.0)
    assert r1.allowed is True
    assert r1.remaining == 0

    # Bucket full
    r2 = await redis_backend.acquire(key, rule, cost=1, current_time=300.0)
    assert r2.allowed is False

    # Leaked 2 units after 2 seconds
    r3 = await redis_backend.acquire(key, rule, cost=1, current_time=302.0)
    assert r3.allowed is True


@pytest.mark.asyncio
async def test_redis_reset(redis_backend: RedisBackend) -> None:
    """Verify reset scans and deletes matching Redis keys."""
    rule = RateLimitRule(limit=2, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
    key = "redis:reset:key"

    await redis_backend.acquire(key, rule, cost=2, current_time=100.0)
    blocked = await redis_backend.acquire(key, rule, cost=1, current_time=100.0)
    assert blocked.allowed is False

    await redis_backend.reset(key)

    res = await redis_backend.acquire(key, rule, cost=1, current_time=100.0)
    assert res.allowed is True


@pytest.mark.asyncio
async def test_redis_fallback_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure transparent fallback to in-memory storage when Redis connection fails."""
    broken_backend = RedisBackend(
        redis_url="redis://localhost:9999/0",
        fallback_on_error=True,
    )

    # Monkeypatch eval to simulate connection failure
    async def mock_fail(*args: object, **kwargs: object) -> None:
        raise RedisConnectionError("Simulated connection dropped")

    monkeypatch.setattr(broken_backend._redis, "eval", mock_fail)

    rule = RateLimitRule(limit=2, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
    # Should not raise; smoothly handled by fallback InMemoryBackend
    res1 = await broken_backend.acquire("fallback:key", rule, cost=1)
    assert res1.allowed is True

    res2 = await broken_backend.acquire("fallback:key", rule, cost=1)
    assert res2.allowed is True

    res3 = await broken_backend.acquire("fallback:key", rule, cost=1)
    assert res3.allowed is False

    await broken_backend.close()


@pytest.mark.asyncio
async def test_redis_raise_error_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure BackendError is raised when fallback_on_error is False."""
    strict_backend = RedisBackend(
        redis_url="redis://localhost:9999/0",
        fallback_on_error=False,
    )

    async def mock_fail(*args: object, **kwargs: object) -> None:
        raise RedisConnectionError("Connection refused")

    monkeypatch.setattr(strict_backend._redis, "eval", mock_fail)

    rule = RateLimitRule(limit=5, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
    with pytest.raises(BackendError):
        await strict_backend.acquire("fail:key", rule)

    await strict_backend.close()
