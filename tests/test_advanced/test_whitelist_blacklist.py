"""Tests for whitelist and blacklist filtering rules."""

import pytest

from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import FilterRule
from rate_limiter.exceptions import BlacklistedError
from rate_limiter.keys.header import ApiKeyStrategy
from rate_limiter.keys.user import UserKeyStrategy
from rate_limiter.limiter import RateLimiter
from tests.conftest import make_mock_request


@pytest.mark.asyncio
async def test_blacklist_ip_and_key() -> None:
    """Ensure blacklisted IP and API key trigger BlacklistedError."""
    backend = InMemoryBackend()
    filters = FilterRule(
        blacklisted_ips={"203.0.113.50"},
        blacklisted_api_keys={"malicious_token"},
        blacklisted_users={"blocked_user_99"},
    )
    limiter = RateLimiter(backend=backend, filter_rule=filters)

    # Blacklisted IP
    req_ip = make_mock_request(client_host="203.0.113.50")
    with pytest.raises(BlacklistedError):
        await limiter.check(req_ip)

    # Blacklisted API Key
    req_key = make_mock_request(headers={"x-api-key": "malicious_token"})
    with pytest.raises(BlacklistedError):
        await limiter.check(req_key, key_strategy=ApiKeyStrategy())

    # Blacklisted User
    req_user = make_mock_request()
    req_user.state.user = {"id": "blocked_user_99", "is_authenticated": True}
    with pytest.raises(BlacklistedError):
        await limiter.check(req_user, key_strategy=UserKeyStrategy())


@pytest.mark.asyncio
async def test_whitelist_ip_api_key_path() -> None:
    """Ensure whitelisted identifiers bypass quota restrictions."""
    backend = InMemoryBackend()
    filters = FilterRule(
        whitelisted_ips={"192.168.1.1"},
        whitelisted_api_keys={"vip_partner"},
        whitelisted_paths={"/metrics"},
    )
    limiter = RateLimiter(backend=backend, filter_rule=filters)

    # Whitelisted IP
    req_ip = make_mock_request(client_host="192.168.1.1")
    res_ip = await limiter.check(req_ip)
    assert res_ip.allowed is True
    assert res_ip.algorithm == "whitelisted"

    # Whitelisted API Key
    req_vip = make_mock_request(headers={"x-api-key": "vip_partner"})
    res_vip = await limiter.check(req_vip, key_strategy=ApiKeyStrategy())
    assert res_vip.allowed is True
    assert res_vip.algorithm == "whitelisted"

    # Whitelisted Path
    req_path = make_mock_request(path="/metrics")
    res_path = await limiter.check(req_path)
    assert res_path.allowed is True
    assert res_path.algorithm == "whitelisted"
