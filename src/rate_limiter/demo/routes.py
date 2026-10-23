"""Routes for the rate limiter demonstration FastAPI service.

Demonstrates all 5 rate limiting algorithms, custom cost models,
tiered access quotas, and diverse key extraction strategies.
"""

from typing import Any

from fastapi import APIRouter, Header, Query, Request

from rate_limiter.config import AlgorithmType
from rate_limiter.decorators import rate_limit
from rate_limiter.keys.composite import CompositeKeyStrategy
from rate_limiter.keys.header import ApiKeyStrategy
from rate_limiter.keys.ip import IPKeyStrategy
from rate_limiter.keys.user import UserKeyStrategy

router = APIRouter()


@router.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """Health check endpoint. Bypasses rate limits via whitelist."""
    return {"status": "ok", "service": "rate-limiter-demo"}


@router.get("/api/status", tags=["System"])
async def get_limiter_status(request: Request) -> dict[str, Any]:
    """Inspect current rate limit state and headers for the calling client."""
    result = getattr(request.state, "rate_limit_result", None)
    return {
        "client": getattr(request.client, "host", "unknown"),
        "path": request.url.path,
        "rate_limited": result is not None,
        "quota": {
            "limit": getattr(result, "limit", None),
            "remaining": getattr(result, "remaining", None),
            "reset_after": getattr(result, "reset_after", None),
            "algorithm": getattr(result, "algorithm", None),
        }
        if result
        else None,
    }


# 1. Fixed Window Algorithm Demonstration
@router.get("/api/fixed-window", tags=["Algorithms"])
@rate_limit(limit=5, period=10.0, algorithm=AlgorithmType.FIXED_WINDOW)
async def fixed_window_endpoint(request: Request) -> dict[str, Any]:
    """Fixed Window limiter: 5 requests per 10 seconds."""
    return {
        "message": "Fixed Window algorithm check passed",
        "limit": "5 req / 10s",
        "algorithm": "fixed_window",
    }


# 2. Sliding Window Log Algorithm Demonstration
@router.get("/api/sliding-log", tags=["Algorithms"])
@rate_limit(limit=5, period=10.0, algorithm=AlgorithmType.SLIDING_WINDOW_LOG)
async def sliding_log_endpoint(request: Request) -> dict[str, Any]:
    """Sliding Window Log: 5 requests per 10s (exact log precision)."""
    return {
        "message": "Sliding Window Log algorithm check passed",
        "limit": "5 req / 10s",
        "algorithm": "sliding_window_log",
    }


# 3. Sliding Window Counter Algorithm Demonstration
@router.get("/api/sliding-counter", tags=["Algorithms"])
@rate_limit(limit=10, period=15.0, algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER)
async def sliding_counter_endpoint(request: Request) -> dict[str, Any]:
    """Sliding Window Counter: 10 requests per 15s (rolling approximation)."""
    return {
        "message": "Sliding Window Counter algorithm check passed",
        "limit": "10 req / 15s",
        "algorithm": "sliding_window_counter",
    }


# 4. Token Bucket Algorithm Demonstration
@router.get("/api/token-bucket", tags=["Algorithms"])
@rate_limit(limit=5, period=10.0, algorithm=AlgorithmType.TOKEN_BUCKET, burst=10)
async def token_bucket_endpoint(request: Request) -> dict[str, Any]:
    """Token Bucket: 5 req/10s refill with burst capacity up to 10."""
    return {
        "message": "Token Bucket algorithm check passed",
        "limit": "5 req / 10s (burst capacity: 10)",
        "algorithm": "token_bucket",
    }


# 5. Leaky Bucket Algorithm Demonstration
@router.get("/api/leaky-bucket", tags=["Algorithms"])
@rate_limit(limit=5, period=10.0, algorithm=AlgorithmType.LEAKY_BUCKET, burst=8)
async def leaky_bucket_endpoint(request: Request) -> dict[str, Any]:
    """Leaky Bucket: smooths traffic to 5 req/10s leak rate with bucket capacity of 8."""
    return {
        "message": "Leaky Bucket algorithm check passed",
        "limit": "5 req / 10s leak rate (capacity: 8)",
        "algorithm": "leaky_bucket",
    }


# 6. Cost-based Limiting Demonstration
@router.post("/api/costly", tags=["Advanced"])
@rate_limit(limit=20, period=60.0, cost=5)
async def costly_endpoint(request: Request) -> dict[str, Any]:
    """Heavy operation consuming 5 quota units per call."""
    return {
        "message": "Costly endpoint executed",
        "cost": 5,
        "detail": "Consumed 5 quota units from your pool of 20.",
    }


# 7. Tier-based Limiting Demonstration
@router.get("/api/tiered", tags=["Advanced"])
async def tiered_endpoint(
    request: Request,
    x_user_tier: str | None = Header(default="free", alias="X-User-Tier"),
) -> dict[str, Any]:
    """Dynamic rate limit based on resolved user tier (free, standard, premium, enterprise)."""
    result = getattr(request.state, "rate_limit_result", None)
    return {
        "message": "Tiered rate limit check passed",
        "tier": x_user_tier,
        "remaining": getattr(result, "remaining", None),
        "limit": getattr(result, "limit", None),
    }


# 8. API Key Strategy Demonstration
@router.get("/api/by-api-key", tags=["Key Strategies"])
@rate_limit(
    limit=10,
    period=30.0,
    key_strategy=ApiKeyStrategy(),
)
async def api_key_endpoint(
    request: Request,
    api_key: str | None = Query(default=None, alias="api_key"),
) -> dict[str, Any]:
    """Rate limited by API Key (via X-API-Key header or api_key query param)."""
    return {
        "message": "API key quota verified",
        "strategy": "ApiKeyStrategy",
    }


# 9. User ID Strategy Demonstration
@router.get("/api/by-user", tags=["Key Strategies"])
@rate_limit(
    limit=15,
    period=30.0,
    key_strategy=UserKeyStrategy(fallback_to_anonymous=True),
)
async def user_id_endpoint(
    request: Request,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> dict[str, Any]:
    """Rate limited per user ID."""
    return {
        "message": "User quota verified",
        "user_id": x_user_id or "anonymous",
        "strategy": "UserKeyStrategy",
    }


# 10. Composite Key Strategy Demonstration
@router.get("/api/composite", tags=["Key Strategies"])
@rate_limit(
    limit=8,
    period=20.0,
    key_strategy=CompositeKeyStrategy([IPKeyStrategy(), ApiKeyStrategy(fallback="public")]),
)
async def composite_key_endpoint(request: Request) -> dict[str, Any]:
    """Rate limited by IP + API Key composite partition."""
    return {
        "message": "Composite key quota verified",
        "strategy": "CompositeKeyStrategy([IPKeyStrategy, ApiKeyStrategy])",
    }
