"""Tests for tiered rate limiting (Free, Standard, Premium, Enterprise)."""

import pytest

from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule, Tier, get_default_tier_rules
from rate_limiter.limiter import RateLimiter
from tests.conftest import make_mock_request


@pytest.mark.asyncio
async def test_dynamic_tier_resolution() -> None:
    """Verify rate limits adjust dynamically based on client tier."""
    backend = InMemoryBackend()
    tier_rules = {
        Tier.FREE.value: RateLimitRule(limit=2, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW),
        Tier.PREMIUM.value: RateLimitRule(
            limit=10, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW
        ),
    }

    def resolve_tier(req: object) -> str:
        headers = getattr(req, "headers", {})
        val = headers.get("x-tier", "free")
        return str(val)

    limiter = RateLimiter(
        backend=backend,
        tier_rules=tier_rules,
        tier_resolver=resolve_tier,
    )

    # Free tier client: limit is 2
    free_req = make_mock_request(client_host="10.0.0.1", headers={"x-tier": "free"})
    r1 = await limiter.check(free_req)
    assert r1.allowed is True
    assert r1.limit == 2

    r2 = await limiter.check(free_req)
    assert r2.allowed is True

    r3 = await limiter.check(free_req)
    assert r3.allowed is False

    # Premium tier client: limit is 10
    premium_req = make_mock_request(client_host="10.0.0.2", headers={"x-tier": "premium"})
    for _ in range(5):
        rp = await limiter.check(premium_req)
        assert rp.allowed is True
        assert rp.limit == 10


@pytest.mark.asyncio
async def test_async_tier_resolver() -> None:
    """Ensure coroutine tier resolvers are properly awaited."""
    backend = InMemoryBackend()

    async def async_tier_resolver(req: object) -> str:
        return "enterprise"

    limiter = RateLimiter(
        backend=backend,
        tier_rules=get_default_tier_rules(),
        tier_resolver=async_tier_resolver,
    )

    req = make_mock_request()
    res = await limiter.check(req)
    assert res.allowed is True
    # Default enterprise rule limit is 5000
    assert res.limit == 5000
