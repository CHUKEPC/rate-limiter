"""FastAPI demonstration application entry point.

Initializes the API server, configures Redis/In-memory storage backends,
registers the rate limiting middleware, whitelists system routes, and loads routes.
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from rate_limiter.backends.base import BaseBackend
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.backends.redis import RedisBackend
from rate_limiter.config import FilterRule, RateLimitRule, get_default_tier_rules
from rate_limiter.decorators import set_default_limiter
from rate_limiter.demo.routes import router
from rate_limiter.limiter import RateLimiter
from rate_limiter.middleware.fastapi import RateLimitMiddleware


def create_limiter() -> tuple[RateLimiter, BaseBackend]:
    """Create and configure the demonstration RateLimiter instance."""
    redis_url = os.getenv("REDIS_URL")

    backend: BaseBackend
    if redis_url:
        backend = RedisBackend(
            redis_url=redis_url,
            fallback_on_error=True,
            prefix="demo_rate_limit:",
        )
    else:
        backend = InMemoryBackend()

    # Configure whitelist and blacklist
    filters = FilterRule(
        whitelisted_paths={"/health", "/docs", "/openapi.json", "/redoc"},
        blacklisted_ips={"198.51.100.1"},  # Example RFC 5737 test IP
        blacklisted_api_keys={"malicious-key-blocked"},
    )

    # Dynamic tier resolver inspecting X-User-Tier header
    def resolve_tier(request: Request) -> str:
        tier_header = request.headers.get("x-user-tier")
        if tier_header:
            return tier_header.lower()
        return "free"

    limiter = RateLimiter(
        backend=backend,
        default_rule=RateLimitRule(limit=60, period=60.0),
        filter_rule=filters,
        tier_rules=get_default_tier_rules(),
        tier_resolver=resolve_tier,
    )

    # Make this limiter the default for route decorators
    set_default_limiter(limiter)

    return limiter, backend


limiter_instance, backend_instance = create_limiter()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing backend connection lifecycle."""
    yield
    await backend_instance.close()


app = FastAPI(
    title="API Rate Limiter Demo",
    description=(
        "Production-ready API Rate Limiter demonstrating 5 algorithms "
        "(Fixed Window, Sliding Window Log, Sliding Window Counter, "
        "Token Bucket, Leaky Bucket), Redis/In-memory backends, and tiered quotas."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Register pure ASGI rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    limiter=limiter_instance,
    include_headers=True,
)

# Mount endpoints
app.include_router(router)
