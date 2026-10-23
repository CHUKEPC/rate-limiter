"""Unit tests for the Leaky Bucket algorithm."""

import pytest

from rate_limiter.algorithms.leaky_bucket import LeakyBucketAlgorithm
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule


@pytest.mark.asyncio
async def test_leaky_bucket_traffic_shaping(memory_backend: InMemoryBackend) -> None:
    """Test water level increments, capacity overflow, and steady leak rate."""
    algo = LeakyBucketAlgorithm(backend=memory_backend)
    # 5 units leak per 5s => 1 unit/sec, capacity of 5 units
    rule = RateLimitRule(
        limit=5,
        period=5.0,
        burst=5,
        algorithm=AlgorithmType.LEAKY_BUCKET,
    )
    key = "user:lb:1"
    start = 100.0

    assert algo.name == AlgorithmType.LEAKY_BUCKET.value

    # Fill bucket to max capacity (5 units)
    r1 = await algo.evaluate(key, rule, cost=5, current_time=start)
    assert r1.allowed is True
    assert r1.remaining == 0

    # Bucket is full: immediate next request rejected
    r2 = await algo.evaluate(key, rule, cost=1, current_time=start)
    assert r2.allowed is False
    assert r2.remaining == 0
    assert r2.retry_after == 1  # 1 unit needs to leak at 1 unit/sec = 1s

    # Advance 2 seconds => 2 units leaked, current water = 3
    # Next request of cost 2: 3 + 2 <= 5 => accepted!
    r3 = await algo.evaluate(key, rule, cost=2, current_time=start + 2.0)
    assert r3.allowed is True
    assert r3.remaining == 0  # water is back to 5
