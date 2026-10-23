"""HTTP response header generation for rate limiting status.

This module formats standard rate limit response headers adhering to both
customary conventions (X-RateLimit-*) and IETF draft standards (RateLimit-*).
"""

import time

from rate_limiter.config import RateLimitResult


def build_rate_limit_headers(
    result: RateLimitResult,
    include_retry_after: bool = True,
    current_time: float | None = None,
    use_ietf_standard: bool = False,
) -> dict[str, str]:
    """Generate HTTP response headers indicating rate limit quotas.

    Args:
        result: Outcome of the rate limit evaluation.
        include_retry_after: Whether to include Retry-After header on denial.
        current_time: Reference unix timestamp, defaults to time.time().
        use_ietf_standard: If True, also includes RFC draft RateLimit-* headers.

    Returns:
        Dictionary containing string header names mapped to string values.
    """
    now = current_time if current_time is not None else time.time()
    reset_epoch = int(now + result.reset_after)

    headers: dict[str, str] = {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(reset_epoch),
    }

    if not result.allowed and include_retry_after:
        headers["Retry-After"] = str(result.retry_after)

    if use_ietf_standard:
        headers["RateLimit-Limit"] = str(result.limit)
        headers["RateLimit-Remaining"] = str(result.remaining)
        headers["RateLimit-Reset"] = str(max(1, int(result.reset_after)))

    return headers
