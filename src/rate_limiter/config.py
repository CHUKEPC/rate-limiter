"""Configuration, rule definitions, and tier models for rate limiting.

This module provides Pydantic models and enumeration types for rate limit rules,
tiered allocations, result tracking, and filtering rules (whitelists/blacklists).
"""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AlgorithmType(StrEnum):
    """Supported rate limiting algorithm identifiers."""

    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"


class Tier(StrEnum):
    """Default rate limit tiers for user categorization."""

    ANONYMOUS = "anonymous"
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class RateLimitRule(BaseModel):
    """Specification of a rate limiting quota and algorithm behavior.

    Attributes:
        limit: Maximum number of operations permitted within the period.
        period: Time window length in seconds.
        cost: Default quota consumption for this rule.
        algorithm: Algorithm used to evaluate compliance.
        burst: Maximum burst capacity for token and leaky bucket algorithms.
            Defaults to limit if not specified.
    """

    limit: int = Field(default=100, gt=0, description="Max allowed quota in period")
    period: float = Field(default=60.0, gt=0.0, description="Window duration in seconds")
    cost: int = Field(default=1, ge=1, description="Quota consumed per request")
    algorithm: AlgorithmType = Field(
        default=AlgorithmType.SLIDING_WINDOW_COUNTER,
        description="Algorithm type to enforce",
    )
    burst: int | None = Field(
        default=None,
        ge=1,
        description="Burst capacity for token/leaky bucket (defaults to limit)",
    )

    @field_validator("burst", mode="after")
    @classmethod
    def validate_burst(cls, v: int | None, info: Any) -> int | None:
        """Ensure burst capacity is at least equal to limit if set."""
        limit = info.data.get("limit")
        if v is not None and isinstance(limit, int) and v < limit:
            return limit
        return v

    @property
    def effective_burst(self) -> int:
        """Return the burst capacity or the limit if burst was not set."""
        return self.burst if self.burst is not None else self.limit


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a rate limit check and consumption attempt.

    Attributes:
        allowed: Whether the request was permitted.
        limit: Configured maximum quota.
        remaining: Quota units remaining in current window.
        reset_after: Floating seconds until window reset or replenishment.
        retry_after: Whole seconds to wait before attempting another request.
        key: Identifier key evaluated.
        algorithm: Name of algorithm applied.
        cost: Quota units consumed by this evaluation.
    """

    allowed: bool
    limit: int
    remaining: int
    reset_after: float
    retry_after: int
    key: str
    algorithm: str
    cost: int = 1

    @classmethod
    def create(
        cls,
        allowed: bool,
        limit: int,
        remaining: int,
        reset_after: float,
        key: str,
        algorithm: str,
        cost: int = 1,
    ) -> "RateLimitResult":
        """Factory method computing retry_after consistently.

        Args:
            allowed: True if granted, False if blocked.
            limit: Maximum rate quota.
            remaining: Units left after operation.
            reset_after: Float duration in seconds.
            key: Evaluation key.
            algorithm: Algorithm identifier.
            cost: Tokens consumed.

        Returns:
            Instantiated RateLimitResult.
        """
        clamped_reset = max(0.0, reset_after)
        retry_after = 0 if allowed else max(1, math.ceil(clamped_reset))
        return cls(
            allowed=allowed,
            limit=limit,
            remaining=max(0, remaining),
            reset_after=clamped_reset,
            retry_after=retry_after,
            key=key,
            algorithm=algorithm,
            cost=cost,
        )


class FilterRule(BaseModel):
    """Rules for bypassing rate checks (whitelist) or denying access (blacklist).

    Attributes:
        whitelisted_ips: IP addresses that bypass rate limits.
        whitelisted_api_keys: API keys that bypass rate limits.
        whitelisted_users: User identifiers that bypass rate limits.
        whitelisted_paths: Endpoint URL paths that bypass rate limits.
        blacklisted_ips: IP addresses that are instantly rejected.
        blacklisted_api_keys: API keys that are instantly rejected.
        blacklisted_users: User identifiers that are instantly rejected.
    """

    whitelisted_ips: set[str] = Field(default_factory=set)
    whitelisted_api_keys: set[str] = Field(default_factory=set)
    whitelisted_users: set[str] = Field(default_factory=set)
    whitelisted_paths: set[str] = Field(default_factory=set)

    blacklisted_ips: set[str] = Field(default_factory=set)
    blacklisted_api_keys: set[str] = Field(default_factory=set)
    blacklisted_users: set[str] = Field(default_factory=set)

    def is_blacklisted(
        self,
        ip: str | None = None,
        api_key: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        """Check if any provided identifier matches a blacklist entry."""
        if ip and ip in self.blacklisted_ips:
            return True
        if api_key and api_key in self.blacklisted_api_keys:
            return True
        return bool(user_id and user_id in self.blacklisted_users)

    def is_whitelisted(
        self,
        ip: str | None = None,
        api_key: str | None = None,
        user_id: str | None = None,
        path: str | None = None,
    ) -> bool:
        """Check if any provided identifier matches a whitelist entry."""
        if path and (path in self.whitelisted_paths or path.rstrip("/") in self.whitelisted_paths):
            return True
        if ip and ip in self.whitelisted_ips:
            return True
        if api_key and api_key in self.whitelisted_api_keys:
            return True
        return bool(user_id and user_id in self.whitelisted_users)


def get_default_tier_rules() -> dict[str, RateLimitRule]:
    """Provide standard out-of-the-box rate limit rules for common tiers.

    Returns:
        Dictionary mapping tier name to RateLimitRule.
    """
    return {
        Tier.ANONYMOUS.value: RateLimitRule(
            limit=20,
            period=60.0,
            algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER,
        ),
        Tier.FREE.value: RateLimitRule(
            limit=60,
            period=60.0,
            algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER,
        ),
        Tier.STANDARD.value: RateLimitRule(
            limit=300,
            period=60.0,
            algorithm=AlgorithmType.TOKEN_BUCKET,
            burst=400,
        ),
        Tier.PREMIUM.value: RateLimitRule(
            limit=1200,
            period=60.0,
            algorithm=AlgorithmType.TOKEN_BUCKET,
            burst=1500,
        ),
        Tier.ENTERPRISE.value: RateLimitRule(
            limit=5000,
            period=60.0,
            algorithm=AlgorithmType.TOKEN_BUCKET,
            burst=6000,
        ),
    }
