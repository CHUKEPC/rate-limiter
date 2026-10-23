"""Decorator for applying rate limits to specific endpoint handlers.

Provides the @rate_limit decorator which can override global middleware settings
or enforce fine-grained endpoint-specific limits, algorithms, costs, and key strategies.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from rate_limiter.config import AlgorithmType, RateLimitRule
from rate_limiter.exceptions import ConfigurationError, RateLimitExceeded
from rate_limiter.keys.base import BaseKeyStrategy
from rate_limiter.limiter import RateLimiter

F = TypeVar("F", bound=Callable[..., Any])

# Default module-level fallback limiter
_default_limiter: RateLimiter | None = None


def get_default_limiter() -> RateLimiter:
    """Retrieve or initialize the global default RateLimiter."""
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = RateLimiter()
    return _default_limiter


def set_default_limiter(limiter: RateLimiter) -> None:
    """Set the global default RateLimiter instance."""
    global _default_limiter
    _default_limiter = limiter


def rate_limit(
    limit: int | None = None,
    period: float | None = None,
    algorithm: AlgorithmType | str | None = None,
    cost: int = 1,
    burst: int | None = None,
    rule: RateLimitRule | None = None,
    key_strategy: BaseKeyStrategy | None = None,
    limiter: RateLimiter | None = None,
) -> Callable[[F], F]:
    """Decorator to apply custom rate limiting to an asynchronous route function.

    Args:
        limit: Maximum requests permitted within the period.
        period: Time window duration in seconds.
        algorithm: Rate limiting algorithm identifier.
        cost: Quota cost for this endpoint.
        burst: Burst capacity for token or leaky bucket.
        rule: Direct RateLimitRule instance (takes precedence if provided).
        key_strategy: Custom key extraction strategy for this endpoint.
        limiter: Custom RateLimiter instance (uses global default if omitted).

    Returns:
        Decorated route handler.
    """
    if rule is not None:
        effective_rule = rule
    elif limit is not None and period is not None:
        algo_enum = (
            AlgorithmType(algorithm)
            if algorithm
            else AlgorithmType.SLIDING_WINDOW_COUNTER
        )
        effective_rule = RateLimitRule(
            limit=limit,
            period=period,
            algorithm=algo_enum,
            cost=cost,
            burst=burst,
        )
    else:
        raise ConfigurationError("Either 'rule' or both 'limit' and 'period' must be provided.")

    def decorator(func: F) -> F:
        # Attach rate limiting metadata for middleware introspection
        func_obj = cast("Any", func)
        func_obj._rate_limit_rule = effective_rule
        func_obj._rate_limit_cost = cost
        func_obj._rate_limit_key_strategy = key_strategy
        func_obj._rate_limit_explicit = True

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Locate Request object among positional or keyword arguments
            request: Any = None
            for arg in args:
                if hasattr(arg, "headers") and hasattr(arg, "client"):
                    request = arg
                    break
            if request is None:
                for _k, v in kwargs.items():
                    if hasattr(v, "headers") and hasattr(v, "client"):
                        request = v
                        break

            active_limiter = limiter or get_default_limiter()

            if request is not None:
                # If middleware already processed this explicit route, avoid double counting
                already_processed = getattr(
                    getattr(request, "state", None), "_rate_limited_by_middleware", False
                )
                if not already_processed:
                    res = await active_limiter.check(
                        request=request,
                        rule=effective_rule,
                        cost=cost,
                        key_strategy=key_strategy,
                    )
                    if hasattr(request, "state"):
                        request.state.rate_limit_result = res

                    if not res.allowed:
                        raise RateLimitExceeded(
                            limit=res.limit,
                            remaining=res.remaining,
                            reset_after=res.reset_after,
                            retry_after=res.retry_after,
                            key=res.key,
                        )

            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
