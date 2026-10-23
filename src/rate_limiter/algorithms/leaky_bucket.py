"""Leaky Bucket rate limiting algorithm.

In the Leaky Bucket algorithm, incoming requests add water drops to a bucket of
finite capacity (burst). The bucket leaks water at a constant rate (limit / period).
If the bucket overflows, incoming requests are rejected.
This smooths bursty traffic and forces a steady, deterministic output rate.
"""

from rate_limiter.algorithms.base import BaseAlgorithm
from rate_limiter.config import AlgorithmType, RateLimitResult, RateLimitRule


class LeakyBucketAlgorithm(BaseAlgorithm):
    """Leaky Bucket rate limiting algorithm for traffic shaping."""

    @property
    def name(self) -> str:
        """Algorithm identifier."""
        return AlgorithmType.LEAKY_BUCKET.value

    async def evaluate(
        self,
        key: str,
        rule: RateLimitRule,
        cost: int = 1,
        current_time: float | None = None,
    ) -> RateLimitResult:
        """Evaluate quota via leaky bucket algorithm on the backend."""
        now = self._get_time(current_time)
        return await self.backend.acquire_leaky_bucket(
            key=key,
            limit=rule.limit,
            period=rule.period,
            burst=rule.effective_burst,
            cost=cost,
            current_time=now,
        )
