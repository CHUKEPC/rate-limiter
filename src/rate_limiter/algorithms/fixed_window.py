"""Fixed Window Counter rate limiting algorithm.

In the Fixed Window algorithm, time is divided into static windows (e.g. 1 minute).
Incoming requests increment a single integer counter for the current window.
Simple and low-overhead, but may allow up to 2x the limit at window boundaries.
"""

from rate_limiter.algorithms.base import BaseAlgorithm
from rate_limiter.config import AlgorithmType, RateLimitResult, RateLimitRule


class FixedWindowAlgorithm(BaseAlgorithm):
    """Fixed Window Counter algorithm."""

    @property
    def name(self) -> str:
        """Algorithm identifier."""
        return AlgorithmType.FIXED_WINDOW.value

    async def evaluate(
        self,
        key: str,
        rule: RateLimitRule,
        cost: int = 1,
        current_time: float | None = None,
    ) -> RateLimitResult:
        """Evaluate quota via fixed window counter on the backend."""
        now = self._get_time(current_time)
        return await self.backend.acquire_fixed_window(
            key=key,
            limit=rule.limit,
            period=rule.period,
            cost=cost,
            current_time=now,
        )
