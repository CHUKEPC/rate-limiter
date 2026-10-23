"""Unit tests for the Fixed Window Counter algorithm."""

import pytest

from rate_limiter.algorithms.fixed_window import FixedWindowAlgorithm
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule


@pytest.mark.asyncio
async def test_fixed_window_basic_flow(memory_backend: InMemoryBackend) -> None:
    """Test standard quota consumption and exhaustion within a fixed window."""
    algo = FixedWindowAlgorithm(backend=memory_backend)
    rule = RateLimitRule(limit=3, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
    key = "user:fixed:1"
    start_time = 1000.0

    assert algo.name == AlgorithmType.FIXED_WINDOW.value

    # First request
    r1 = await algo.evaluate(key, rule, cost=1, current_time=start_time)
    assert r1.allowed is True
    assert r1.remaining == 2
    assert r1.limit == 3
    assert r1.retry_after == 0

    # Second request
    r2 = await algo.evaluate(key, rule, cost=1, current_time=start_time + 1.0)
    assert r2.allowed is True
    assert r2.remaining == 1

    # Third request
    r3 = await algo.evaluate(key, rule, cost=1, current_time=start_time + 2.0)
    assert r3.allowed is True
    assert r3.remaining == 0

    # Fourth request: should be blocked
    r4 = await algo.evaluate(key, rule, cost=1, current_time=start_time + 3.0)
    assert r4.allowed is False
    assert r4.remaining == 0
    assert r4.retry_after > 0


@pytest.mark.asyncio
async def test_fixed_window_resets_on_new_period(memory_backend: InMemoryBackend) -> None:
    """Ensure quota refreshes once time advances into the next window."""
    algo = FixedWindowAlgorithm(backend=memory_backend)
    rule = RateLimitRule(limit=2, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
    key = "user:fixed:2"
    t0 = 1000.0

    # Consume all quota
    await algo.evaluate(key, rule, cost=2, current_time=t0)
    blocked = await algo.evaluate(key, rule, cost=1, current_time=t0 + 2.0)
    assert blocked.allowed is False

    # Jump to next window (t0 + 10.1s => window index changes from 100 to 101)
    t1 = 1010.1
    next_win = await algo.evaluate(key, rule, cost=1, current_time=t1)
    assert next_win.allowed is True
    assert next_win.remaining == 1


@pytest.mark.asyncio
async def test_fixed_window_cost_support(memory_backend: InMemoryBackend) -> None:
    """Verify that requests consuming multiple units are checked accurately."""
    algo = FixedWindowAlgorithm(backend=memory_backend)
    rule = RateLimitRule(limit=10, period=20.0, algorithm=AlgorithmType.FIXED_WINDOW)
    key = "user:fixed:cost"

    # Consume cost 7
    r1 = await algo.evaluate(key, rule, cost=7, current_time=100.0)
    assert r1.allowed is True
    assert r1.remaining == 3

    # Attempt to consume cost 4 (exceeds remaining 3)
    r2 = await algo.evaluate(key, rule, cost=4, current_time=101.0)
    assert r2.allowed is False
    assert r2.remaining == 3
