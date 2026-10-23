"""Abstract base storage backend for rate limiting.

This module declares the interface that all rate limiting backends must implement,
guaranteeing uniform behavior across in-memory, Redis, and custom storage engines.
"""

import time
from abc import ABC, abstractmethod
from typing import Any

from rate_limiter.config import AlgorithmType, RateLimitResult, RateLimitRule
from rate_limiter.exceptions import ConfigurationError


class BaseBackend(ABC):
    """Abstract base class for rate limiter backends."""

    async def acquire(
        self,
        key: str,
        rule: RateLimitRule,
        cost: int = 1,
        current_time: float | None = None,
    ) -> RateLimitResult:
        """Evaluate and consume quota for the given key and rule.

        Dispatches to the specific algorithm implementation method based on
        rule.algorithm.

        Args:
            key: Unique identifier to rate limit.
            rule: Rate limit rule specification.
            cost: Number of tokens or count to consume.
            current_time: Unix timestamp (seconds), defaults to time.time().

        Returns:
            RateLimitResult with decision and quota metrics.

        Raises:
            ConfigurationError: If the specified algorithm is not supported.
        """
        now = current_time if current_time is not None else time.time()
        effective_cost = cost if cost > 0 else rule.cost
        burst = rule.effective_burst

        match rule.algorithm:
            case AlgorithmType.FIXED_WINDOW:
                return await self.acquire_fixed_window(
                    key=key,
                    limit=rule.limit,
                    period=rule.period,
                    cost=effective_cost,
                    current_time=now,
                )
            case AlgorithmType.SLIDING_WINDOW_LOG:
                return await self.acquire_sliding_window_log(
                    key=key,
                    limit=rule.limit,
                    period=rule.period,
                    cost=effective_cost,
                    current_time=now,
                )
            case AlgorithmType.SLIDING_WINDOW_COUNTER:
                return await self.acquire_sliding_window_counter(
                    key=key,
                    limit=rule.limit,
                    period=rule.period,
                    cost=effective_cost,
                    current_time=now,
                )
            case AlgorithmType.TOKEN_BUCKET:
                return await self.acquire_token_bucket(
                    key=key,
                    limit=rule.limit,
                    period=rule.period,
                    burst=burst,
                    cost=effective_cost,
                    current_time=now,
                )
            case AlgorithmType.LEAKY_BUCKET:
                return await self.acquire_leaky_bucket(
                    key=key,
                    limit=rule.limit,
                    period=rule.period,
                    burst=burst,
                    cost=effective_cost,
                    current_time=now,
                )
            case _:
                raise ConfigurationError(f"Unsupported algorithm type: {rule.algorithm}")

    @abstractmethod
    async def acquire_fixed_window(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Evaluate quota using the Fixed Window algorithm."""
        pass

    @abstractmethod
    async def acquire_sliding_window_log(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Evaluate quota using the Sliding Window Log algorithm."""
        pass

    @abstractmethod
    async def acquire_sliding_window_counter(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Evaluate quota using the Sliding Window Counter algorithm."""
        pass

    @abstractmethod
    async def acquire_token_bucket(
        self,
        key: str,
        limit: int,
        period: float,
        burst: int,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Evaluate quota using the Token Bucket algorithm."""
        pass

    @abstractmethod
    async def acquire_leaky_bucket(
        self,
        key: str,
        limit: int,
        period: float,
        burst: int,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Evaluate quota using the Leaky Bucket algorithm."""
        pass

    @abstractmethod
    async def reset(self, key: str) -> None:
        """Reset or clear all rate limit data for a specific key."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Release underlying connections or resources."""
        pass

    async def __aenter__(self) -> "BaseBackend":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
