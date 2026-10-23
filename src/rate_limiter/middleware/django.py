"""Django middleware integration for rate limiting.

Supports both synchronous and asynchronous Django request handling pipelines,
injecting rate limit headers into HttpResponse objects and returning JsonResponse
with status 429 Too Many Requests when limits are breached.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

from rate_limiter.config import RateLimitResult, RateLimitRule
from rate_limiter.exceptions import BlacklistedError
from rate_limiter.headers import build_rate_limit_headers
from rate_limiter.limiter import RateLimiter


class DjangoRateLimitMiddleware:
    """Rate limiting middleware for Django applications."""

    def __init__(
        self,
        get_response: Callable[[Any], Any],
        limiter: RateLimiter,
        default_rule: RateLimitRule | None = None,
        include_headers: bool = True,
    ) -> None:
        """Initialize Django rate limiting middleware.

        Args:
            get_response: Django view or next middleware callable.
            limiter: Configured RateLimiter instance.
            default_rule: Baseline rate limit rule for all Django requests.
            include_headers: Whether to append rate limit headers to responses.
        """
        self.get_response = get_response
        self.limiter = limiter
        self.default_rule = default_rule
        self.include_headers = include_headers
        self._is_coroutine = asyncio.iscoroutinefunction(get_response)

    def __call__(self, request: Any) -> Any:
        """Synchronous request processing entry point."""
        if self._is_coroutine:
            return self.__acall__(request)

        # Run async limiter check in synchronous thread
        try:
            result = asyncio.run(self.limiter.check(request=request, rule=self.default_rule))
        except BlacklistedError as exc:
            return self._build_django_json_response(
                {"error": "Forbidden", "message": exc.message}, status=403
            )

        if not result.allowed:
            return self._build_429_response(result)

        response = self.get_response(request)
        if self.include_headers and response is not None:
            self._apply_headers(response, result)

        return response

    async def __acall__(self, request: Any) -> Any:
        """Asynchronous request processing entry point."""
        try:
            result = await self.limiter.check(request=request, rule=self.default_rule)
        except BlacklistedError as exc:
            return self._build_django_json_response(
                {"error": "Forbidden", "message": exc.message}, status=403
            )

        if not result.allowed:
            return self._build_429_response(result)

        response = await self.get_response(request)
        if self.include_headers and response is not None:
            self._apply_headers(response, result)

        return response

    def _apply_headers(self, response: Any, result: RateLimitResult) -> None:
        """Attach X-RateLimit-* headers to Django HttpResponse."""
        headers = build_rate_limit_headers(result, include_retry_after=False)
        for key, val in headers.items():
            response[key] = val

    def _build_429_response(self, result: RateLimitResult) -> Any:
        """Construct Django 429 JsonResponse."""
        data = {
            "error": "Rate limit exceeded",
            "message": f"Rate limit exceeded. Retry after {result.retry_after}s.",
            "limit": result.limit,
            "remaining": result.remaining,
            "retry_after": result.retry_after,
        }
        headers = build_rate_limit_headers(result, include_retry_after=True)
        return self._build_django_json_response(data, status=429, headers=headers)

    def _build_django_json_response(
        self,
        data: dict[str, Any],
        status: int,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Create JSON response object adhering to Django HttpResponse interface."""
        try:
            from django.http import JsonResponse  # type: ignore[import-not-found]

            response = JsonResponse(data, status=status)
        except ImportError:
            # Duck-typed response when Django is not installed in the testing environment
            class DuckResponse:
                def __init__(self, content: bytes, status_code: int) -> None:
                    self.content = content
                    self.status_code = status_code
                    self.headers: dict[str, str] = {"Content-Type": "application/json"}

                def __setitem__(self, key: str, value: str) -> None:
                    self.headers[key] = value

                def __getitem__(self, key: str) -> str:
                    return self.headers[key]

            response = DuckResponse(json.dumps(data).encode("utf-8"), status_code=status)

        if headers:
            for k, v in headers.items():
                response[k] = v

        return response
