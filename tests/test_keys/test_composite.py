"""Unit tests for CompositeKeyStrategy and CustomKeyStrategy."""

import pytest

from rate_limiter.keys.composite import CompositeKeyStrategy, CustomKeyStrategy
from rate_limiter.keys.header import ApiKeyStrategy
from rate_limiter.keys.ip import IPKeyStrategy
from tests.conftest import make_mock_request


@pytest.mark.asyncio
async def test_composite_key_strategy() -> None:
    """Test combining multiple strategies into a multi-part key."""
    strat = CompositeKeyStrategy(
        strategies=[
            IPKeyStrategy(),
            ApiKeyStrategy(fallback="guest"),
        ],
        delimiter=":",
        prefix="composite:",
    )

    req = make_mock_request(client_host="10.20.30.40", headers={"x-api-key": "pro-user-1"})
    result = await strat.extract(req)
    assert result == "composite:ip:10.20.30.40:apikey:pro-user-1"


@pytest.mark.asyncio
async def test_custom_key_strategy() -> None:
    """Test synchronous and asynchronous custom extractor callables."""

    # Synchronous extractor
    def sync_extractor(req: object) -> str:
        return "tenant_org_42"

    strat_sync = CustomKeyStrategy(extractor=sync_extractor, prefix="tenant:")
    req = make_mock_request()
    assert await strat_sync.extract(req) == "tenant:tenant_org_42"

    # Asynchronous extractor
    async def async_extractor(req: object) -> str:
        return "async_session_99"

    strat_async = CustomKeyStrategy(extractor=async_extractor, prefix="sess:")
    assert await strat_async.extract(req) == "sess:async_session_99"
