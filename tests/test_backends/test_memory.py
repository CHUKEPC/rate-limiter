"""Unit tests for the InMemoryBackend."""

import pytest

from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitRule
from rate_limiter.exceptions import ConfigurationError


@pytest.mark.asyncio
async def test_memory_backend_dispatch_and_unsupported_algo(
    memory_backend: InMemoryBackend,
) -> None:
    """Test generic acquire dispatch and error handling for unknown algorithms."""
    # Test valid dispatch
    rule = RateLimitRule(limit=5, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
    res = await memory_backend.acquire("key:mem:1", rule)
    assert res.allowed is True
    assert res.remaining == 4

    # Create dummy rule with invalid algorithm to test ConfigurationError
    invalid_rule = RateLimitRule(limit=5, period=10.0)
    object.__setattr__(invalid_rule, "algorithm", "unsupported_magic_algo")

    with pytest.raises(ConfigurationError):
        await memory_backend.acquire("key:bad", invalid_rule)


@pytest.mark.asyncio
async def test_memory_backend_context_manager() -> None:
    """Verify backend operates cleanly as an async context manager."""
    async with InMemoryBackend() as backend:
        rule = RateLimitRule(limit=2, period=10.0)
        res = await backend.acquire("ctx:1", rule)
        assert res.allowed is True


@pytest.mark.asyncio
async def test_memory_backend_reset_all_algorithms(memory_backend: InMemoryBackend) -> None:
    """Verify reset clears state across all algorithm buckets."""
    key = "test:multi:algo"
    now = 1000.0

    # Populate all buckets
    await memory_backend.acquire_fixed_window(key, 1, 10.0, 1, now)
    await memory_backend.acquire_sliding_window_log(key, 1, 10.0, 1, now)
    await memory_backend.acquire_sliding_window_counter(key, 1, 10.0, 1, now)
    await memory_backend.acquire_token_bucket(key, 1, 10.0, 1, 1, now)
    await memory_backend.acquire_leaky_bucket(key, 1, 10.0, 1, 1, now)

    # Reset
    await memory_backend.reset(key)

    # Check they can all acquire again
    f_res = await memory_backend.acquire_fixed_window(key, 1, 10.0, 1, now)
    assert f_res.allowed is True

    l_res = await memory_backend.acquire_sliding_window_log(key, 1, 10.0, 1, now)
    assert l_res.allowed is True
