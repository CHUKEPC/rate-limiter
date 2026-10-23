"""Integration tests verifying the FastAPI demonstration app routes."""

import httpx
import pytest

from rate_limiter.demo.app import app


@pytest.mark.asyncio
async def test_demo_health() -> None:
    """Test health check route."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok", "service": "rate-limiter-demo"}


@pytest.mark.asyncio
async def test_demo_status() -> None:
    """Test rate limit status reporting endpoint."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/status")
        assert res.status_code == 200
        data = res.json()
        assert "client" in data
        assert "quota" in data


@pytest.mark.asyncio
async def test_demo_algorithms_endpoints() -> None:
    """Test all 5 algorithm demonstration routes."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Fixed Window
        r_fw = await client.get("/api/fixed-window")
        assert r_fw.status_code == 200
        assert r_fw.json()["algorithm"] == "fixed_window"

        # Sliding Window Log
        r_swl = await client.get("/api/sliding-log")
        assert r_swl.status_code == 200
        assert r_swl.json()["algorithm"] == "sliding_window_log"

        # Sliding Window Counter
        r_swc = await client.get("/api/sliding-counter")
        assert r_swc.status_code == 200
        assert r_swc.json()["algorithm"] == "sliding_window_counter"

        # Token Bucket
        r_tb = await client.get("/api/token-bucket")
        assert r_tb.status_code == 200
        assert r_tb.json()["algorithm"] == "token_bucket"

        # Leaky Bucket
        r_lb = await client.get("/api/leaky-bucket")
        assert r_lb.status_code == 200
        assert r_lb.json()["algorithm"] == "leaky_bucket"


@pytest.mark.asyncio
async def test_demo_advanced_endpoints() -> None:
    """Test costly and tiered rate limited routes."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Costly endpoint
        r_cost = await client.post("/api/costly")
        assert r_cost.status_code == 200
        assert r_cost.json()["cost"] == 5

        # Tiered endpoint with custom header
        r_tier = await client.get("/api/tiered", headers={"X-User-Tier": "premium"})
        assert r_tier.status_code == 200
        assert r_tier.json()["tier"] == "premium"


@pytest.mark.asyncio
async def test_demo_key_strategies_endpoints() -> None:
    """Test API key, User ID, and composite key demonstration routes."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # By API Key
        r_key = await client.get("/api/by-api-key", headers={"X-API-Key": "demo-key-123"})
        assert r_key.status_code == 200
        assert r_key.json()["strategy"] == "ApiKeyStrategy"

        # By User ID
        r_user = await client.get("/api/by-user", headers={"X-User-ID": "alice_99"})
        assert r_user.status_code == 200
        assert r_user.json()["user_id"] == "alice_99"

        # Composite key
        r_comp = await client.get("/api/composite", headers={"X-API-Key": "partner-45"})
        assert r_comp.status_code == 200
