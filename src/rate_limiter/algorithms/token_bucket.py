"""Token Bucket rate limiting algorithm.

The Token Bucket algorithm maintains a bucket filled with tokens up to capacity (burst).
Tokens are continuously replenished at a steady rate (limit / period).
Incoming requests consume tokens; requests are permitted if sufficient tokens exist.
Allows temporary burst traffic while maintaining an average rate limit.
"""

from rate_limiter.algorithms.base import BaseAlgorithm
from rate_limiter.config import AlgorithmType, RateLimitResult, RateLimitRule


class TokenBucketAlgorithm(BaseAlgorithm):
    """Token Bucket rate limiting algorithm with burst capacity."""

    @property
    def name(self) -> str:
        """Algorithm identifier."""
        return AlgorithmType.TOKEN_BUCKET.value

    async def evaluate(
        self,
        key: str,
        rule: RateLimitRule,
        cost: int = 1,
        current_time: float | None = None,
    ) -> RateLimitResult:
        """Evaluate quota via token bucket algorithm on the backend."""
        now = self._get_time(current_time)
        return await self.backend.acquire_token_bucket(
            key=key,
            limit=rule.limit,
            period=rule.period,
            burst=rule.effective_burst,
            cost=cost,
            current_time=now,
        )
