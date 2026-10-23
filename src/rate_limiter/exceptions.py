"""Exceptions for the rate limiter library.

This module defines all custom exception classes used across backends,
algorithms, key extraction strategies, and middleware integrations.
"""

from typing import Any


class RateLimiterError(Exception):
    """Base class for all rate limiter exceptions."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RateLimitExceeded(RateLimiterError):  # noqa: N818
    """Raised when an operation exceeds its configured rate limit.

    Attributes:
        limit: The maximum number of allowed calls within the period.
        remaining: The remaining quota (typically 0 when exceeded).
        reset_after: Time in seconds until the current limit resets.
        retry_after: Integer seconds to wait before retrying (ceil of reset_after).
        key: The rate limit key that triggered this exception.
        detail: Human-readable message describing the limit status.
    """

    def __init__(
        self,
        limit: int,
        remaining: int = 0,
        reset_after: float = 0.0,
        retry_after: int = 0,
        key: str = "",
        detail: str | None = None,
    ) -> None:
        self.limit = limit
        self.remaining = remaining
        self.reset_after = max(0.0, reset_after)
        self.retry_after = max(1, retry_after if retry_after > 0 else int(self.reset_after) + 1)
        self.key = key
        default_detail = (
            f"Rate limit exceeded: {limit} requests permitted. Retry after {self.retry_after}s."
        )
        self.detail = detail or default_detail
        super().__init__(self.detail)


class BackendError(RateLimiterError):
    """Raised when an error occurs in the storage backend (e.g., Redis)."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class ConfigurationError(RateLimiterError):
    """Raised when invalid configuration parameters are provided."""

    pass


class KeyExtractionError(RateLimiterError):
    """Raised when a key strategy cannot extract a key from a request."""

    def __init__(self, strategy_name: str, reason: str, request_info: Any = None) -> None:
        super().__init__(f"Failed to extract rate limit key via {strategy_name}: {reason}")
        self.strategy_name = strategy_name
        self.reason = reason
        self.request_info = request_info


class BlacklistedError(RateLimiterError):
    """Raised when a client is rejected due to a blacklist rule."""

    def __init__(self, identifier: str, reason: str = "Client is blacklisted") -> None:
        super().__init__(f"Access denied: {reason} (identifier={identifier})")
        self.identifier = identifier
        self.reason = reason


# Suffix-compliant alias
RateLimitExceededError = RateLimitExceeded
