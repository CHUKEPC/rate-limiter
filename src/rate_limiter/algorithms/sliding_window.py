"""Sliding Window rate limiting algorithms.

Provides both:
1. SlidingWindowLogAlgorithm: Tracks exact request timestamps in a sliding window log.
   Offers 100% precision with O(N) memory consumption.
2. SlidingWindowCounterAlgorithm: Approximates sliding window counts by weighting
   the previous and current fixed windows. O(1) memory and high performance.
"""

from rate_limiter.algorithms.base import BaseAlgorithm
from rate_limiter.config import AlgorithmType, RateLimitResult, RateLimitRule


class SlidingWindowLogAlgorithm(BaseAlgorithm):
    """Sliding Window Log algorithm providing exact sliding window tracking."""

    @property
    def name(self) -> str:
        """Algorithm identifier."""
        return AlgorithmType.SLIDING_WINDOW_LOG.value

    async def evaluate(
        self,
        key: str,
        rule: RateLimitRule,
        cost: int = 1,
        current_time: float | None = None,
    ) -> RateLimitResult:
        """Evaluate quota via sliding window log on the backend."""
        now = self._get_time(current_time)
        return await self.backend.acquire_sliding_window_log(
            key=key,
            limit=rule.limit,
            period=rule.period,
            cost=cost,
            current_time=now,
        )


class SlidingWindowCounterAlgorithm(BaseAlgorithm):
    """Sliding Window Counter algorithm estimating rolling quota consumption."""

    @property
    def name(self) -> str:
        """Algorithm identifier."""
        return AlgorithmType.SLIDING_WINDOW_COUNTER.value

    async def evaluate(
        self,
        key: str,
        rule: RateLimitRule,
        cost: int = 1,
        current_time: float | None = None,
    ) -> RateLimitResult:
        """Evaluate quota via sliding window counter on the backend."""
        now = self._get_time(current_time)
        return await self.backend.acquire_sliding_window_counter(
            key=key,
            limit=rule.limit,
            period=rule.period,
            cost=cost,
            current_time=now,
        )


# Backward-compatible alias
SlidingWindowAlgorithm = SlidingWindowCounterAlgorithm
