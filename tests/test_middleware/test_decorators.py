"""Unit tests for the @rate_limit endpoint decorator."""

import pytest

from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule
from rate_limiter.decorators import rate_limit, set_default_limiter
from rate_limiter.exceptions import ConfigurationError, RateLimitExceeded
from rate_limiter.keys.header import ApiKeyStrategy
from rate_limiter.limiter import RateLimiter
from tests.conftest import make_mock_request


@pytest.mark.asyncio
async def test_decorator_enforcement() -> None:
    """Test @rate_limit enforcing quotas on an async handler function."""
    backend = InMemoryBackend()
    limiter = RateLimiter(backend=backend)
    set_default_limiter(limiter)

    @rate_limit(limit=2, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
    async def sample_handler(request: object) -> str:
        return "success"

    req = make_mock_request()

    # Call 1: success
    res1 = await sample_handler(request=req)
    assert res1 == "success"

    # Call 2: success
    res2 = await sample_handler(request=req)
    assert res2 == "success"

    # Call 3: raises RateLimitExceeded
    with pytest.raises(RateLimitExceeded) as exc_info:
        await sample_handler(request=req)

    assert exc_info.value.limit == 2
    assert exc_info.value.remaining == 0
    assert exc_info.value.retry_after > 0


@pytest.mark.asyncio
async def test_decorator_with_explicit_rule_and_key_strategy() -> None:
    """Test @rate_limit with custom rule object and specific key strategy."""
    backend = InMemoryBackend()
    limiter = RateLimiter(backend=backend)

    rule = RateLimitRule(limit=1, period=5.0, algorithm=AlgorithmType.TOKEN_BUCKET)
    key_strat = ApiKeyStrategy(fallback="default_api_key")

    @rate_limit(rule=rule, key_strategy=key_strat, limiter=limiter)
    async def api_handler(request: object) -> str:
        return "api ok"

    req = make_mock_request(headers={"x-api-key": "pro-customer-1"})

    assert await api_handler(request=req) == "api ok"

    # Second call should exceed
    with pytest.raises(RateLimitExceeded):
        await api_handler(request=req)


def test_decorator_configuration_error() -> None:
    """Ensure ConfigurationError is raised when neither rule nor limit+period provided."""
    with pytest.raises(ConfigurationError):

        @rate_limit()
        async def invalid_handler(request: object) -> str:
            return "never"
