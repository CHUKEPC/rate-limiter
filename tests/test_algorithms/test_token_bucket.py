"""Unit tests for the Token Bucket algorithm."""

import pytest

from rate_limiter.algorithms.token_bucket import TokenBucketAlgorithm
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule


@pytest.mark.asyncio
async def test_token_bucket_burst_and_refill(memory_backend: InMemoryBackend) -> None:
    """Test token consumption, burst capacity, and continuous refill."""
    algo = TokenBucketAlgorithm(backend=memory_backend)
    # 10 tokens per 10s => 1 token/sec refill, burst capacity of 15 tokens
    rule = RateLimitRule(
        limit=10,
        period=10.0,
        burst=15,
        algorithm=AlgorithmType.TOKEN_BUCKET,
    )
    key = "user:tb:1"
    start_time = 500.0

    assert algo.name == AlgorithmType.TOKEN_BUCKET.value

    # Burst all 15 tokens at once
    r1 = await algo.evaluate(key, rule, cost=15, current_time=start_time)
    assert r1.allowed is True
    assert r1.remaining == 0

    # Immediate next request should fail because bucket is empty
    r2 = await algo.evaluate(key, rule, cost=1, current_time=start_time)
    assert r2.allowed is False
    assert r2.remaining == 0
    assert r2.retry_after == 1  # 1 token needed at 1 token/sec = 1s

    # Advance time by 3 seconds => 3 tokens refilled
    r3 = await algo.evaluate(key, rule, cost=2, current_time=start_time + 3.0)
    assert r3.allowed is True
    assert r3.remaining == 1  # 3 refilled - 2 consumed = 1 remaining


@pytest.mark.asyncio
async def test_token_bucket_capacity_cap(memory_backend: InMemoryBackend) -> None:
    """Ensure tokens never accumulate beyond configured burst capacity."""
    algo = TokenBucketAlgorithm(backend=memory_backend)
    rule = RateLimitRule(limit=5, period=5.0, burst=10, algorithm=AlgorithmType.TOKEN_BUCKET)
    key = "user:tb:cap"

    # Start and consume 2 tokens
    r1 = await algo.evaluate(key, rule, cost=2, current_time=100.0)
    assert r1.allowed is True
    assert r1.remaining == 8

    # Wait 1000 seconds (vastly exceeds capacity)
    r2 = await algo.evaluate(key, rule, cost=1, current_time=1100.0)
    assert r2.allowed is True
    # Tokens capped at burst (10) - 1 = 9
    assert r2.remaining == 9
