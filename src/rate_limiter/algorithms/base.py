"""Abstract base class for rate limiting algorithms.

Each algorithm wraps a storage backend and provides a standardized interface
for evaluating incoming request quotas according to specific rate-limiting rules.
"""

import time
from abc import ABC, abstractmethod

from rate_limiter.backends.base import BaseBackend
from rate_limiter.config import RateLimitResult, RateLimitRule


class BaseAlgorithm(ABC):
    """Abstract base algorithm strategy for rate limiting.

    Attributes:
        backend: The storage backend (e.g. Memory, Redis) executing the check.
    """

    def __init__(self, backend: BaseBackend) -> None:
        self.backend = backend

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique algorithm identifier name."""
        pass

    @abstractmethod
    async def evaluate(
        self,
        key: str,
        rule: RateLimitRule,
        cost: int = 1,
        current_time: float | None = None,
    ) -> RateLimitResult:
        """Evaluate and consume quota using this algorithm.

        Args:
            key: Rate limiter unique key.
            rule: Configured rate limit rule.
            cost: Number of tokens or requests to consume.
            current_time: Optional reference unix timestamp.

        Returns:
            RateLimitResult containing approval decision and quota metrics.
        """
        pass

    def _get_time(self, current_time: float | None) -> float:
        """Return provided time or current wall clock timestamp."""
        return current_time if current_time is not None else time.time()
