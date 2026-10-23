"""Tests for cost-based rate limiting."""

import pytest

from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule
from rate_limiter.limiter import RateLimiter
from tests.conftest import make_mock_request


@pytest.mark.asyncio
async def test_cost_based_limiting() -> None:
    """Ensure varying costs consume quota accurately."""
    backend = InMemoryBackend()
    rule = RateLimitRule(limit=10, period=60.0, algorithm=AlgorithmType.TOKEN_BUCKET, burst=10)
    limiter = RateLimiter(backend=backend, default_rule=rule)

    req = make_mock_request()

    # Cheap call: cost=1
    r1 = await limiter.check(req, cost=1)
    assert r1.allowed is True
    assert r1.remaining == 9
    assert r1.cost == 1

    # Heavy call: cost=5
    r2 = await limiter.check(req, cost=5)
    assert r2.allowed is True
    assert r2.remaining == 4
    assert r2.cost == 5

    # Excess call: cost=6 (only 4 remain)
    r3 = await limiter.check(req, cost=6)
    assert r3.allowed is False
    assert r3.remaining == 4
