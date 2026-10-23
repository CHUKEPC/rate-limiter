"""In-memory storage backend for rate limiting.

This backend provides a zero-dependency, thread-safe and async-safe implementation
of all 5 rate limiting algorithms. It is suitable for single-node deployments,
testing, development, and fallback when remote backends are unreachable.
"""

import asyncio
import math

from rate_limiter.backends.base import BaseBackend
from rate_limiter.config import AlgorithmType, RateLimitResult


class InMemoryBackend(BaseBackend):
    """In-memory rate limit storage backend utilizing asyncio locking.

    Maintains in-process states for fixed window counters, sliding logs,
    sliding counters, token buckets, and leaky buckets.
    """

    def __init__(self) -> None:
        super().__init__()
        self._lock = asyncio.Lock()
        # key -> (window_index, count)
        self._fixed_windows: dict[str, tuple[int, int]] = {}
        # key -> list of float timestamps
        self._sliding_logs: dict[str, list[float]] = {}
        # key -> (current_window_index, current_count, previous_count)
        self._sliding_counters: dict[str, tuple[int, int, int]] = {}
        # key -> (tokens, last_refill_timestamp)
        self._token_buckets: dict[str, tuple[float, float]] = {}
        # key -> (water_level, last_leak_timestamp)
        self._leaky_buckets: dict[str, tuple[float, float]] = {}

    async def acquire_fixed_window(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Fixed window counter algorithm in memory."""
        window_index = int(current_time // period)
        window_end = (window_index + 1) * period
        reset_after = max(0.0, window_end - current_time)

        async with self._lock:
            stored_window, current_count = self._fixed_windows.get(key, (window_index, 0))
            if stored_window != window_index:
                current_count = 0

            if current_count + cost <= limit:
                new_count = current_count + cost
                self._fixed_windows[key] = (window_index, new_count)
                remaining = limit - new_count
                return RateLimitResult.create(
                    allowed=True,
                    limit=limit,
                    remaining=remaining,
                    reset_after=reset_after,
                    key=key,
                    algorithm=AlgorithmType.FIXED_WINDOW.value,
                    cost=cost,
                )
            else:
                remaining = max(0, limit - current_count)
                return RateLimitResult.create(
                    allowed=False,
                    limit=limit,
                    remaining=remaining,
                    reset_after=reset_after,
                    key=key,
                    algorithm=AlgorithmType.FIXED_WINDOW.value,
                    cost=cost,
                )

    async def acquire_sliding_window_log(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Sliding window log algorithm storing exact timestamps in memory."""
        window_start = current_time - period

        async with self._lock:
            logs = self._sliding_logs.get(key, [])
            # Evict timestamps older than the sliding window start
            logs = [ts for ts in logs if ts > window_start]

            current_count = len(logs)
            if current_count + cost <= limit:
                # Append cost timestamps
                logs.extend([current_time] * cost)
                self._sliding_logs[key] = logs
                remaining = limit - (current_count + cost)
                # Reset after is time until the earliest log entry expires
                reset_after = (logs[0] + period - current_time) if logs else period
                return RateLimitResult.create(
                    allowed=True,
                    limit=limit,
                    remaining=remaining,
                    reset_after=max(0.0, reset_after),
                    key=key,
                    algorithm=AlgorithmType.SLIDING_WINDOW_LOG.value,
                    cost=cost,
                )
            else:
                self._sliding_logs[key] = logs
                remaining = max(0, limit - current_count)
                reset_after = (logs[0] + period - current_time) if logs else period
                return RateLimitResult.create(
                    allowed=False,
                    limit=limit,
                    remaining=remaining,
                    reset_after=max(0.0, reset_after),
                    key=key,
                    algorithm=AlgorithmType.SLIDING_WINDOW_LOG.value,
                    cost=cost,
                )

    async def acquire_sliding_window_counter(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Sliding window counter combining current and previous windows."""
        current_window = int(current_time // period)
        window_start = current_window * period
        time_into_current = current_time - window_start
        weight = time_into_current / period  # Fraction of current window passed

        async with self._lock:
            stored_window, cur_count, prev_count = self._sliding_counters.get(
                key, (current_window, 0, 0)
            )

            if stored_window == current_window:
                # Current window matches
                pass
            elif stored_window == current_window - 1:
                # Transitioned to immediate next window
                prev_count = cur_count
                cur_count = 0
            else:
                # Gap greater than 1 window: both expired
                prev_count = 0
                cur_count = 0

            # Approximation: weight of previous window decreases as current progresses
            estimated_count = prev_count * (1.0 - weight) + cur_count
            reset_after = max(0.0, period * (1.0 - weight))

            if estimated_count + cost <= limit:
                cur_count += cost
                self._sliding_counters[key] = (current_window, cur_count, prev_count)
                remaining = max(0, limit - math.floor(estimated_count + cost))
                return RateLimitResult.create(
                    allowed=True,
                    limit=limit,
                    remaining=remaining,
                    reset_after=reset_after,
                    key=key,
                    algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER.value,
                    cost=cost,
                )
            else:
                self._sliding_counters[key] = (current_window, cur_count, prev_count)
                remaining = max(0, limit - math.floor(estimated_count))
                return RateLimitResult.create(
                    allowed=False,
                    limit=limit,
                    remaining=remaining,
                    reset_after=reset_after,
                    key=key,
                    algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER.value,
                    cost=cost,
                )

    async def acquire_token_bucket(
        self,
        key: str,
        limit: int,
        period: float,
        burst: int,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Token bucket algorithm supporting burst allowances."""
        refill_rate = limit / period
        capacity = float(burst)

        async with self._lock:
            stored = self._token_buckets.get(key)
            if stored is None:
                current_tokens = capacity
                last_update = current_time
            else:
                tokens, last_update = stored
                delta = max(0.0, current_time - last_update)
                current_tokens = min(capacity, tokens + delta * refill_rate)

            if current_tokens >= cost:
                new_tokens = current_tokens - cost
                self._token_buckets[key] = (new_tokens, current_time)
                # If tokens are low, calculate time to refill cost tokens
                reset_after = (cost - new_tokens) / refill_rate if new_tokens < cost else 0.0
                return RateLimitResult.create(
                    allowed=True,
                    limit=limit,
                    remaining=math.floor(new_tokens),
                    reset_after=max(0.0, reset_after),
                    key=key,
                    algorithm=AlgorithmType.TOKEN_BUCKET.value,
                    cost=cost,
                )
            else:
                self._token_buckets[key] = (current_tokens, current_time)
                deficit = cost - current_tokens
                reset_after = deficit / refill_rate
                return RateLimitResult.create(
                    allowed=False,
                    limit=limit,
                    remaining=math.floor(current_tokens),
                    reset_after=max(0.0, reset_after),
                    key=key,
                    algorithm=AlgorithmType.TOKEN_BUCKET.value,
                    cost=cost,
                )

    async def acquire_leaky_bucket(
        self,
        key: str,
        limit: int,
        period: float,
        burst: int,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Leaky bucket algorithm for smoothing burst traffic to constant leak rate."""
        leak_rate = limit / period
        capacity = float(burst)

        async with self._lock:
            stored = self._leaky_buckets.get(key)
            if stored is None:
                water_level = 0.0
                last_update = current_time
            else:
                prev_water, last_update = stored
                delta = max(0.0, current_time - last_update)
                water_level = max(0.0, prev_water - (delta * leak_rate))

            if water_level + cost <= capacity:
                new_water = water_level + cost
                self._leaky_buckets[key] = (new_water, current_time)
                remaining = max(0, math.floor(capacity - new_water))
                reset_after = new_water / leak_rate
                return RateLimitResult.create(
                    allowed=True,
                    limit=limit,
                    remaining=remaining,
                    reset_after=max(0.0, reset_after),
                    key=key,
                    algorithm=AlgorithmType.LEAKY_BUCKET.value,
                    cost=cost,
                )
            else:
                self._leaky_buckets[key] = (water_level, current_time)
                remaining = max(0, math.floor(capacity - water_level))
                excess = (water_level + cost) - capacity
                reset_after = excess / leak_rate
                return RateLimitResult.create(
                    allowed=False,
                    limit=limit,
                    remaining=remaining,
                    reset_after=max(0.0, reset_after),
                    key=key,
                    algorithm=AlgorithmType.LEAKY_BUCKET.value,
                    cost=cost,
                )

    async def reset(self, key: str) -> None:
        """Reset all rate limit data associated with the given key."""
        async with self._lock:
            self._fixed_windows.pop(key, None)
            self._sliding_logs.pop(key, None)
            self._sliding_counters.pop(key, None)
            self._token_buckets.pop(key, None)
            self._leaky_buckets.pop(key, None)

    async def close(self) -> None:
        """Clear all internal in-memory rate limiting structures."""
        async with self._lock:
            self._fixed_windows.clear()
            self._sliding_logs.clear()
            self._sliding_counters.clear()
            self._token_buckets.clear()
            self._leaky_buckets.clear()
