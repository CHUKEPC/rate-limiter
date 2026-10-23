"""Redis-backed distributed storage backend for rate limiting.

This backend executes atomic Lua scripts on a Redis cluster or single node,
enabling horizontally scaled rate limiting with exact synchronization across
multiple application instances and worker processes.
"""

import math
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from rate_limiter.backends.base import BaseBackend
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import AlgorithmType, RateLimitResult
from rate_limiter.exceptions import BackendError

# Lua script for atomic Fixed Window evaluation
_LUA_FIXED_WINDOW = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local cost = tonumber(ARGV[2])
local ttl = math.ceil(tonumber(ARGV[3]))

local current = redis.call('INCRBY', key, cost)
if current == cost then
    redis.call('EXPIRE', key, ttl)
end

if current <= limit then
    return {1, limit - current}
else
    redis.call('DECRBY', key, cost)
    local remaining = math.max(0, limit - (current - cost))
    return {0, remaining}
end
"""

# Lua script for atomic Sliding Window Log evaluation
_LUA_SLIDING_WINDOW_LOG = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local period = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
local current_count = redis.call('ZCARD', key)

local earliest_res = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local earliest_score = now
if #earliest_res >= 2 then
    earliest_score = tonumber(earliest_res[2])
end

if current_count + cost <= limit then
    for i = 1, cost do
        local member = tostring(now) .. ':' .. tostring(i) .. ':' .. tostring(redis.call('INCR', key .. ':seq'))
        redis.call('ZADD', key, now, member)
    end
    redis.call('PEXPIRE', key, math.ceil(period * 1000))
    redis.call('PEXPIRE', key .. ':seq', math.ceil(period * 1000))
    local remaining = limit - (current_count + cost)
    return {1, remaining, tostring(earliest_score)}
else
    local remaining = math.max(0, limit - current_count)
    return {0, remaining, tostring(earliest_score)}
end
"""

# Lua script for atomic Sliding Window Counter evaluation
_LUA_SLIDING_WINDOW_COUNTER = """
local current_key = KEYS[1]
local previous_key = KEYS[2]
local limit = tonumber(ARGV[1])
local cost = tonumber(ARGV[2])
local weight = tonumber(ARGV[3])
local ttl = math.ceil(tonumber(ARGV[4]))

local prev_count = tonumber(redis.call('GET', previous_key) or '0')
local cur_count = tonumber(redis.call('GET', current_key) or '0')

local estimated = prev_count * (1.0 - weight) + cur_count

if estimated + cost <= limit then
    local new_cur = redis.call('INCRBY', current_key, cost)
    if new_cur == cost then
        redis.call('EXPIRE', current_key, ttl)
    end
    local remaining = math.max(0, limit - math.floor(estimated + cost))
    return {1, remaining}
else
    local remaining = math.max(0, limit - math.floor(estimated))
    return {0, remaining}
end
"""

# Lua script for atomic Token Bucket evaluation
_LUA_TOKEN_BUCKET = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local period = tonumber(ARGV[2])
local capacity = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local now = tonumber(ARGV[5])
local ttl = math.ceil(tonumber(ARGV[6]))

local refill_rate = limit / period
local data = redis.call('HMGET', key, 'tokens', 'last_update')
local tokens = tonumber(data[1])
local last_update = tonumber(data[2])

if not tokens or not last_update then
    tokens = capacity
    last_update = now
else
    local delta = math.max(0, now - last_update)
    tokens = math.min(capacity, tokens + delta * refill_rate)
end

if tokens >= cost then
    tokens = tokens - cost
    redis.call('HMSET', key, 'tokens', tostring(tokens), 'last_update', tostring(now))
    redis.call('EXPIRE', key, ttl)
    return {1, math.floor(tokens), tostring(tokens)}
else
    redis.call('HMSET', key, 'tokens', tostring(tokens), 'last_update', tostring(now))
    redis.call('EXPIRE', key, ttl)
    local deficit = cost - tokens
    return {0, math.floor(tokens), tostring(deficit)}
end
"""

# Lua script for atomic Leaky Bucket evaluation
_LUA_LEAKY_BUCKET = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local period = tonumber(ARGV[2])
local capacity = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local now = tonumber(ARGV[5])
local ttl = math.ceil(tonumber(ARGV[6]))

local leak_rate = limit / period
local data = redis.call('HMGET', key, 'water', 'last_leak')
local water = tonumber(data[1])
local last_leak = tonumber(data[2])

if not water or not last_leak then
    water = 0.0
    last_leak = now
else
    local delta = math.max(0, now - last_leak)
    water = math.max(0, water - (delta * leak_rate))
end

if water + cost <= capacity then
    water = water + cost
    redis.call('HMSET', key, 'water', tostring(water), 'last_leak', tostring(now))
    redis.call('EXPIRE', key, ttl)
    local remaining = math.max(0, math.floor(capacity - water))
    return {1, remaining, tostring(water)}
else
    redis.call('HMSET', key, 'water', tostring(water), 'last_leak', tostring(now))
    redis.call('EXPIRE', key, ttl)
    local remaining = math.max(0, math.floor(capacity - water))
    local excess = (water + cost) - capacity
    return {0, remaining, tostring(excess)}
end
"""


class RedisBackend(BaseBackend):
    """Distributed Redis storage backend for rate limiting.

    Executes pre-compiled Lua scripts atomically across distributed nodes
    and offers automatic fallback to in-memory storage if Redis becomes unreachable.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "rate_limit:",
        fallback_on_error: bool = True,
        timeout: float = 2.0,
    ) -> None:
        super().__init__()
        self._prefix = prefix
        self._fallback_on_error = fallback_on_error
        self._timeout = timeout
        self._fallback_backend = InMemoryBackend() if fallback_on_error else None

        if redis_client is not None:
            self._redis = redis_client
            self._owns_client = False
        else:
            self._redis = aioredis.from_url(
                redis_url,
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
                decode_responses=True,
            )
            self._owns_client = True

    def _format_key(self, key: str, subkey: str = "") -> str:
        """Namespace a rate limiter key."""
        if subkey:
            return f"{self._prefix}{key}:{subkey}"
        return f"{self._prefix}{key}"

    async def acquire_fixed_window(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Distributed fixed window counter using Redis."""
        window_index = int(current_time // period)
        window_end = (window_index + 1) * period
        reset_after = max(0.0, window_end - current_time)
        redis_key = self._format_key(key, f"fw:{window_index}")

        try:
            res: list[Any] = await self._redis.eval(
                _LUA_FIXED_WINDOW,
                1,
                redis_key,
                limit,
                cost,
                max(1, math.ceil(reset_after) + 2),
            )
            allowed = bool(res[0] == 1)
            remaining = int(res[1])
            return RateLimitResult.create(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_after=reset_after,
                key=key,
                algorithm=AlgorithmType.FIXED_WINDOW.value,
                cost=cost,
            )
        except (RedisError, ConnectionError, OSError) as exc:
            if self._fallback_backend:
                return await self._fallback_backend.acquire_fixed_window(
                    key, limit, period, cost, current_time
                )
            raise BackendError("Redis fixed window check failed", original_error=exc) from exc

    async def acquire_sliding_window_log(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Distributed sliding window log using Redis ZSET."""
        window_start = current_time - period
        redis_key = self._format_key(key, "swl")

        try:
            res: list[Any] = await self._redis.eval(
                _LUA_SLIDING_WINDOW_LOG,
                1,
                redis_key,
                current_time,
                window_start,
                limit,
                cost,
                period,
            )
            allowed = bool(res[0] == 1)
            remaining = int(res[1])
            earliest_score = float(res[2]) if len(res) > 2 else current_time
            reset_after = max(0.0, (earliest_score + period) - current_time)

            return RateLimitResult.create(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_after=reset_after,
                key=key,
                algorithm=AlgorithmType.SLIDING_WINDOW_LOG.value,
                cost=cost,
            )
        except (RedisError, ConnectionError, OSError) as exc:
            if self._fallback_backend:
                return await self._fallback_backend.acquire_sliding_window_log(
                    key, limit, period, cost, current_time
                )
            raise BackendError("Redis sliding log check failed", original_error=exc) from exc

    async def acquire_sliding_window_counter(
        self,
        key: str,
        limit: int,
        period: float,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Distributed sliding window counter approximating rolling limits."""
        current_window = int(current_time // period)
        prev_window = current_window - 1
        window_start = current_window * period
        time_into_current = current_time - window_start
        weight = time_into_current / period
        reset_after = max(0.0, period * (1.0 - weight))

        cur_key = self._format_key(key, f"swc:{current_window}")
        prev_key = self._format_key(key, f"swc:{prev_window}")

        try:
            res: list[Any] = await self._redis.eval(
                _LUA_SLIDING_WINDOW_COUNTER,
                2,
                cur_key,
                prev_key,
                limit,
                cost,
                weight,
                max(1, math.ceil(period * 2)),
            )
            allowed = bool(res[0] == 1)
            remaining = int(res[1])
            return RateLimitResult.create(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_after=reset_after,
                key=key,
                algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER.value,
                cost=cost,
            )
        except (RedisError, ConnectionError, OSError) as exc:
            if self._fallback_backend:
                return await self._fallback_backend.acquire_sliding_window_counter(
                    key, limit, period, cost, current_time
                )
            raise BackendError("Redis sliding counter check failed", original_error=exc) from exc

    async def acquire_token_bucket(
        self,
        key: str,
        limit: int,
        period: float,
        burst: int,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Distributed token bucket algorithm."""
        refill_rate = limit / period
        redis_key = self._format_key(key, "tb")
        ttl = max(1, math.ceil((burst / refill_rate) * 2))

        try:
            res: list[Any] = await self._redis.eval(
                _LUA_TOKEN_BUCKET,
                1,
                redis_key,
                limit,
                period,
                burst,
                cost,
                current_time,
                ttl,
            )
            allowed = bool(res[0] == 1)
            remaining = int(res[1])
            metric_val = float(res[2])

            if allowed:
                tokens_left = metric_val
                reset_after = (cost - tokens_left) / refill_rate if tokens_left < cost else 0.0
            else:
                deficit = metric_val
                reset_after = deficit / refill_rate

            return RateLimitResult.create(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_after=max(0.0, reset_after),
                key=key,
                algorithm=AlgorithmType.TOKEN_BUCKET.value,
                cost=cost,
            )
        except (RedisError, ConnectionError, OSError) as exc:
            if self._fallback_backend:
                return await self._fallback_backend.acquire_token_bucket(
                    key, limit, period, burst, cost, current_time
                )
            raise BackendError("Redis token bucket check failed", original_error=exc) from exc

    async def acquire_leaky_bucket(
        self,
        key: str,
        limit: int,
        period: float,
        burst: int,
        cost: int,
        current_time: float,
    ) -> RateLimitResult:
        """Distributed leaky bucket algorithm."""
        leak_rate = limit / period
        redis_key = self._format_key(key, "lb")
        ttl = max(1, math.ceil((burst / leak_rate) * 2))

        try:
            res: list[Any] = await self._redis.eval(
                _LUA_LEAKY_BUCKET,
                1,
                redis_key,
                limit,
                period,
                burst,
                cost,
                current_time,
                ttl,
            )
            allowed = bool(res[0] == 1)
            remaining = int(res[1])
            metric_val = float(res[2])

            if allowed:
                water = metric_val
                reset_after = water / leak_rate
            else:
                excess = metric_val
                reset_after = excess / leak_rate

            return RateLimitResult.create(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_after=max(0.0, reset_after),
                key=key,
                algorithm=AlgorithmType.LEAKY_BUCKET.value,
                cost=cost,
            )
        except (RedisError, ConnectionError, OSError) as exc:
            if self._fallback_backend:
                return await self._fallback_backend.acquire_leaky_bucket(
                    key, limit, period, burst, cost, current_time
                )
            raise BackendError("Redis leaky bucket check failed", original_error=exc) from exc

    async def reset(self, key: str) -> None:
        """Delete all Redis keys matching the namespace prefix for the specified key."""
        try:
            pattern = f"{self._prefix}{key}*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except (RedisError, ConnectionError, OSError) as exc:
            if self._fallback_backend:
                await self._fallback_backend.reset(key)
                return
            raise BackendError(f"Failed to reset Redis key {key}", original_error=exc) from exc

    async def close(self) -> None:
        """Close connection to Redis."""
        if self._owns_client:
            await self._redis.aclose()
        if self._fallback_backend:
            await self._fallback_backend.close()
