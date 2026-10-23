"""Unit tests for the Sliding Window Counter algorithm."""

import pytest

from rate_limiter.algorithms.sliding_window import SlidingWindowCounterAlgorithm
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule


@pytest.mark.asyncio
async def test_sliding_window_counter_smoothing(memory_backend: InMemoryBackend) -> None:
    """Test weighted estimation between previous and current window."""
    algo = SlidingWindowCounterAlgorithm(backend=memory_backend)
    rule = RateLimitRule(limit=10, period=60.0, algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER)
    key = "user:swc:1"

    assert algo.name == AlgorithmType.SLIDING_WINDOW_COUNTER.value

    # Fill window 0 (t=10 to t=50, window 0..60) with 10 requests
    for i in range(10):
        res = await algo.evaluate(key, rule, cost=1, current_time=10.0 + i)
        assert res.allowed is True

    # 11th request in window 0 should be blocked
    blocked = await algo.evaluate(key, rule, cost=1, current_time=55.0)
    assert blocked.allowed is False

    # Now step into window 1 at t=75.0 (15 seconds into window 60..120).
    # Weight of current window passed: 15 / 60 = 0.25
    # Weight of previous window: 1.0 - 0.25 = 0.75
    # Estimated previous requests = 10 * 0.75 = 7.5
    # Estimated current = 0
    # Total estimated = 7.5. Since limit is 10, a request of cost 1 gives 8.5 <= 10 -> allowed!
    r_step = await algo.evaluate(key, rule, cost=1, current_time=75.0)
    assert r_step.allowed is True

    # Step to t=130 (more than 1 full window ahead, gap > 1 window):
    # Previous count becomes 0, full capacity available
    r_fresh = await algo.evaluate(key, rule, cost=5, current_time=180.0)
    assert r_fresh.allowed is True
    assert r_fresh.remaining == 5
