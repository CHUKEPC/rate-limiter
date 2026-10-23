"""API Rate Limiter Library.

A flexible, high-performance, and framework-agnostic rate limiting library
with 5 algorithms (Fixed Window, Sliding Window Log, Sliding Window Counter,
Token Bucket, Leaky Bucket), distributed Redis and in-memory backends,
FastAPI and Django middleware, tiered quotas, and composite key extraction strategies.
"""

from rate_limiter.algorithms import (
    BaseAlgorithm,
    FixedWindowAlgorithm,
    LeakyBucketAlgorithm,
    SlidingWindowAlgorithm,
    SlidingWindowCounterAlgorithm,
    SlidingWindowLogAlgorithm,
    TokenBucketAlgorithm,
)
from rate_limiter.backends import BaseBackend, InMemoryBackend, RedisBackend
from rate_limiter.config import (
    AlgorithmType,
    FilterRule,
    RateLimitResult,
    RateLimitRule,
    Tier,
    get_default_tier_rules,
)
from rate_limiter.decorators import rate_limit
from rate_limiter.exceptions import (
    BackendError,
    BlacklistedError,
    ConfigurationError,
    KeyExtractionError,
    RateLimiterError,
    RateLimitExceeded,
)
from rate_limiter.headers import build_rate_limit_headers
from rate_limiter.keys import (
    ApiKeyStrategy,
    BaseKeyStrategy,
    CompositeKeyStrategy,
    CustomKeyStrategy,
    HeaderKeyStrategy,
    IPKeyStrategy,
    UserKeyStrategy,
)
from rate_limiter.limiter import RateLimiter
from rate_limiter.middleware import DjangoRateLimitMiddleware, RateLimitMiddleware

__version__ = "0.1.0"

__all__ = [
    "AlgorithmType",
    "ApiKeyStrategy",
    "BackendError",
    "BaseAlgorithm",
    "BaseBackend",
    "BaseKeyStrategy",
    "BlacklistedError",
    "CompositeKeyStrategy",
    "ConfigurationError",
    "CustomKeyStrategy",
    "DjangoRateLimitMiddleware",
    "FilterRule",
    "FixedWindowAlgorithm",
    "HeaderKeyStrategy",
    "IPKeyStrategy",
    "InMemoryBackend",
    "KeyExtractionError",
    "LeakyBucketAlgorithm",
    "RateLimitExceeded",
    "RateLimitMiddleware",
    "RateLimitResult",
    "RateLimitRule",
    "RateLimiter",
    "RateLimiterError",
    "RedisBackend",
    "SlidingWindowAlgorithm",
    "SlidingWindowCounterAlgorithm",
    "SlidingWindowLogAlgorithm",
    "Tier",
    "TokenBucketAlgorithm",
    "UserKeyStrategy",
    "__version__",
    "build_rate_limit_headers",
    "get_default_tier_rules",
    "rate_limit",
]
