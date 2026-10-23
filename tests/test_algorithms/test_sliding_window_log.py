"""Unit tests for the Sliding Window Log algorithm."""

import pytest

from rate_limiter.algorithms.sliding_window import SlidingWindowLogAlgorithm
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule


@pytest.mark.asyncio
async def test_sliding_window_log_precision(memory_backend: InMemoryBackend) -> None:
    """Verify exact sliding window eviction without fixed boundary issues."""
    algo = SlidingWindowLogAlgorithm(backend=memory_backend)
    rule = RateLimitRule(limit=3, period=10.0, algorithm=AlgorithmType.SLIDING_WINDOW_LOG)
    key = "user:swl:1"

    assert algo.name == AlgorithmType.SLIDING_WINDOW_LOG.value

    # Three requests at t=0, t=2, t=4
    r1 = await algo.evaluate(key, rule, cost=1, current_time=100.0)
    assert r1.allowed is True
    assert r1.remaining == 2

    r2 = await algo.evaluate(key, rule, cost=1, current_time=102.0)
    assert r2.allowed is True
    assert r2.remaining == 1

    r3 = await algo.evaluate(key, rule, cost=1, current_time=104.0)
    assert r3.allowed is True
    assert r3.remaining == 0

    # Request at t=105.0: limit is 3 in 10s, all 3 are within window [95.0, 105.0] -> rejected
    r4 = await algo.evaluate(key, rule, cost=1, current_time=105.0)
    assert r4.allowed is False

    # At t=110.5: request from t=100.0 falls out of the [100.5, 110.5] window.
    # Remaining active timestamps are t=102.0 and t=104.0 (2 requests).
    # New request should be accepted!
    r5 = await algo.evaluate(key, rule, cost=1, current_time=110.5)
    assert r5.allowed is True
    assert r5.remaining == 0  # 102, 104, 110.5 = 3 active


@pytest.mark.asyncio
async def test_sliding_window_log_cost_and_reset(memory_backend: InMemoryBackend) -> None:
    """Test cost consumption and reset behavior for sliding log."""
    algo = SlidingWindowLogAlgorithm(backend=memory_backend)
    rule = RateLimitRule(limit=5, period=10.0, algorithm=AlgorithmType.SLIDING_WINDOW_LOG)
    key = "user:swl:cost"

    # Consume 4 at t=50.0
    res = await algo.evaluate(key, rule, cost=4, current_time=50.0)
    assert res.allowed is True
    assert res.remaining == 1

    # Attempt 2 at t=51.0 (blocked)
    blocked = await algo.evaluate(key, rule, cost=2, current_time=51.0)
    assert blocked.allowed is False
    assert blocked.remaining == 1

    # Reset key
    await memory_backend.reset(key)
    res_after_reset = await algo.evaluate(key, rule, cost=2, current_time=52.0)
    assert res_after_reset.allowed is True
    assert res_after_reset.remaining == 3
