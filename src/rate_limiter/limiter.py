"""Core RateLimiter coordinator managing backends, rules, keys, and filters.

Provides the high-level API orchestrating whitelist/blacklist evaluation,
dynamic tier resolution, key extraction, quota checks, and response header generation.
"""

import inspect
from collections.abc import Callable
from typing import Any

from rate_limiter.backends.base import BaseBackend
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.config import FilterRule, RateLimitResult, RateLimitRule, get_default_tier_rules
from rate_limiter.exceptions import BlacklistedError, RateLimitExceeded
from rate_limiter.keys.base import BaseKeyStrategy
from rate_limiter.keys.ip import IPKeyStrategy


class RateLimiter:
    """Central rate limiter coordinating rules, keys, backends, and tiers."""

    def __init__(
        self,
        backend: BaseBackend | None = None,
        default_rule: RateLimitRule | None = None,
        key_strategy: BaseKeyStrategy | None = None,
        filter_rule: FilterRule | None = None,
        tier_rules: dict[str, RateLimitRule] | None = None,
        tier_resolver: Callable[[Any], Any] | None = None,
        raise_on_exceeded: bool = False,
    ) -> None:
        """Initialize the RateLimiter.

        Args:
            backend: Storage backend; defaults to an InMemoryBackend instance.
            default_rule: Baseline rate limit rule; defaults to 100 req/60s.
            key_strategy: Primary key extractor; defaults to IPKeyStrategy.
            filter_rule: Whitelist and blacklist definitions.
            tier_rules: Mapping from tier identifiers to custom RateLimitRules.
            tier_resolver: Optional callable (request) -> tier_name for tiered limits.
            raise_on_exceeded: If True, check() raises RateLimitExceeded directly.
        """
        self.backend = backend or InMemoryBackend()
        self.default_rule = default_rule or RateLimitRule()
        self.key_strategy = key_strategy or IPKeyStrategy()
        self.filter_rule = filter_rule or FilterRule()
        self.tier_rules = tier_rules if tier_rules is not None else get_default_tier_rules()
        self.tier_resolver = tier_resolver
        self.raise_on_exceeded = raise_on_exceeded

    async def _resolve_rule(self, request: Any, explicit_rule: RateLimitRule | None) -> RateLimitRule:
        """Determine applicable rule considering explicit rule and dynamic tiers."""
        if explicit_rule is not None:
            return explicit_rule

        if self.tier_resolver is not None:
            if inspect.iscoroutinefunction(self.tier_resolver):
                tier = await self.tier_resolver(request)
            else:
                tier = self.tier_resolver(request)

            if tier and self.tier_rules and str(tier) in self.tier_rules:
                return self.tier_rules[str(tier)]

        return self.default_rule

    async def check(
        self,
        request: Any,
        rule: RateLimitRule | None = None,
        cost: int | None = None,
        key_override: str | None = None,
        key_strategy: BaseKeyStrategy | None = None,
    ) -> RateLimitResult:
        """Evaluate rate limit compliance for a request.

        Args:
            request: Incoming HTTP request object.
            rule: Optional explicit rule override for this check.
            cost: Optional quota cost (defaults to rule.cost).
            key_override: Explicit partition key, skipping strategy extraction.
            key_strategy: Strategy override for extracting key from this request.

        Returns:
            RateLimitResult with decision, remaining units, and reset duration.

        Raises:
            BlacklistedError: If client matches any blacklist rule.
            RateLimitExceeded: If rate limit exceeded and raise_on_exceeded is True.
        """
        path = getattr(getattr(request, "url", None), "path", None)

        # 1. Extract Key for tracking & checking
        if key_override is not None:
            partition_key = key_override
        else:
            strategy = key_strategy or self.key_strategy
            partition_key = await strategy.extract(request)

        # Extract potential identifiers for whitelist/blacklist filters
        ip_val = None
        if "ip:" in partition_key:
            ip_val = partition_key.split("ip:", 1)[1]
        elif hasattr(request, "client") and request.client:
            ip_val = getattr(request.client, "host", None)

        api_key_val = None
        if "apikey:" in partition_key:
            api_key_val = partition_key.split("apikey:", 1)[1]

        user_val = None
        if "user:" in partition_key:
            user_val = partition_key.split("user:", 1)[1]

        # 2. Check Blacklist
        if self.filter_rule.is_blacklisted(ip=ip_val, api_key=api_key_val, user_id=user_val):
            raise BlacklistedError(identifier=partition_key)

        # 3. Check Whitelist
        if self.filter_rule.is_whitelisted(
            ip=ip_val, api_key=api_key_val, user_id=user_val, path=path
        ):
            # Whitelisted requests bypass quotas entirely
            return RateLimitResult.create(
                allowed=True,
                limit=999999,
                remaining=999999,
                reset_after=0.0,
                key=partition_key,
                algorithm="whitelisted",
                cost=0,
            )

        # 4. Resolve applicable rule
        effective_rule = await self._resolve_rule(request, rule)
        effective_cost = cost if cost is not None else effective_rule.cost

        # 5. Acquire quota on backend
        result = await self.backend.acquire(
            key=partition_key,
            rule=effective_rule,
            cost=effective_cost,
        )

        if not result.allowed and self.raise_on_exceeded:
            raise RateLimitExceeded(
                limit=result.limit,
                remaining=result.remaining,
                reset_after=result.reset_after,
                retry_after=result.retry_after,
                key=partition_key,
            )

        return result

    async def reset(self, key: str) -> None:
        """Reset rate limit data for a specific key."""
        await self.backend.reset(key)

    async def close(self) -> None:
        """Release backend resources."""
        await self.backend.close()
