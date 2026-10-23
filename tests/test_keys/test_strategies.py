"""Unit tests for IP, Header, API Key, and User key strategies."""

import pytest

from rate_limiter.exceptions import KeyExtractionError
from rate_limiter.keys.header import ApiKeyStrategy, HeaderKeyStrategy
from rate_limiter.keys.ip import IPKeyStrategy
from rate_limiter.keys.user import UserKeyStrategy
from tests.conftest import make_mock_request


@pytest.mark.asyncio
async def test_ip_key_strategy_headers() -> None:
    """Test extracting IP from various proxy headers."""
    strat = IPKeyStrategy()

    # CF-Connecting-IP
    req_cf = make_mock_request(headers={"cf-connecting-ip": "203.0.113.195"})
    assert await strat.extract(req_cf) == "ip:203.0.113.195"

    # X-Real-IP
    req_real = make_mock_request(headers={"x-real-ip": "198.51.100.42"})
    assert await strat.extract(req_real) == "ip:198.51.100.42"

    # X-Forwarded-For with multiple hops
    req_xff = make_mock_request(headers={"x-forwarded-for": "192.0.2.1, 10.0.0.1"})
    assert await strat.extract(req_xff) == "ip:192.0.2.1"

    # Direct client host fallback
    req_direct = make_mock_request(client_host="192.168.1.100")
    assert await strat.extract(req_direct) == "ip:192.168.1.100"


@pytest.mark.asyncio
async def test_ip_key_strategy_error_when_no_fallback() -> None:
    """Raise KeyExtractionError if IP cannot be determined and fallback is None."""
    strat = IPKeyStrategy(fallback=None)
    req = make_mock_request(client_host=None)

    with pytest.raises(KeyExtractionError):
        await strat.extract(req)


@pytest.mark.asyncio
async def test_api_key_strategy() -> None:
    """Test extracting API key from headers and query parameters."""
    strat = ApiKeyStrategy()

    # From X-API-Key header
    req_hdr = make_mock_request(headers={"x-api-key": "secret-token-123"})
    assert await strat.extract(req_hdr) == "apikey:secret-token-123"

    # From query param
    req_qp = make_mock_request(query_string="api_key=query-token-456")
    assert await strat.extract(req_qp) == "apikey:query-token-456"

    # Missing with fallback
    strat_fallback = ApiKeyStrategy(fallback="public-anonymous")
    req_none = make_mock_request()
    assert await strat_fallback.extract(req_none) == "apikey:public-anonymous"

    # Missing without fallback
    with pytest.raises(KeyExtractionError):
        await strat.extract(req_none)


@pytest.mark.asyncio
async def test_header_key_strategy() -> None:
    """Test generic header key extraction."""
    strat = HeaderKeyStrategy(header_name="Authorization")
    req = make_mock_request(headers={"authorization": "Bearer eyJhbGciOi..."})
    assert await strat.extract(req) == "hdr:authorization:Bearer eyJhbGciOi..."


@pytest.mark.asyncio
async def test_user_key_strategy() -> None:
    """Test user identifier extraction from request.state.user."""
    strat = UserKeyStrategy(user_attribute="id")

    req_anon = make_mock_request()
    assert await strat.extract(req_anon) == "user:anonymous"

    # Authenticated user as object
    class MockUser:
        id = "usr_9988"
        is_authenticated = True

    req_auth = make_mock_request()
    req_auth.state.user = MockUser()
    assert await strat.extract(req_auth) == "user:usr_9988"

    # Authenticated user as dictionary
    req_dict = make_mock_request()
    req_dict.state.user = {"id": "usr_dict_12", "is_authenticated": True}
    assert await strat.extract(req_dict) == "user:usr_dict_12"

    # Unauthenticated user without fallback
    strat_strict = UserKeyStrategy(fallback_to_anonymous=False)
    with pytest.raises(KeyExtractionError):
        await strat_strict.extract(req_anon)
