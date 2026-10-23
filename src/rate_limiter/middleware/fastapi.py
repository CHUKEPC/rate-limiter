"""ASGI Middleware for FastAPI and Starlette applications.

Provides high-performance, non-blocking rate limit enforcement, route inspection,
blacklist rejection (403), rate limit headers injection, and 429 Too Many Requests handling.
"""

import json
from collections.abc import Callable
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rate_limiter.config import RateLimitResult, RateLimitRule
from rate_limiter.exceptions import BlacklistedError
from rate_limiter.headers import build_rate_limit_headers
from rate_limiter.limiter import RateLimiter


class RateLimitMiddleware:
    """Pure ASGI rate limiting middleware for FastAPI and Starlette."""

    def __init__(
        self,
        app: ASGIApp,
        limiter: RateLimiter,
        default_rule: RateLimitRule | None = None,
        include_headers: bool = True,
        custom_exceeded_handler: (
            Callable[[Request, RateLimitResult], tuple[int, dict[str, Any]]] | None
        ) = None,
    ) -> None:
        """Initialize RateLimitMiddleware.

        Args:
            app: The ASGI downstream application.
            limiter: RateLimiter coordinator instance.
            default_rule: Optional default rule overriding limiter's baseline.
            include_headers: Whether to attach X-RateLimit-* headers to responses.
            custom_exceeded_handler: Optional custom callback (request, result) -> (status_code, body_dict).
        """
        self.app = app
        self.limiter = limiter
        self.default_rule = default_rule
        self.include_headers = include_headers
        self.custom_exceeded_handler = custom_exceeded_handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI request processor."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        # Inspect endpoint metadata for route-level overrides
        endpoint = scope.get("endpoint")
        rule_override = getattr(endpoint, "_rate_limit_rule", self.default_rule)
        cost_override = getattr(endpoint, "_rate_limit_cost", None)
        key_strategy_override = getattr(endpoint, "_rate_limit_key_strategy", None)

        try:
            result = await self.limiter.check(
                request=request,
                rule=rule_override,
                cost=cost_override,
                key_strategy=key_strategy_override,
            )
        except BlacklistedError as exc:
            # Immediate 403 Forbidden for blacklisted clients
            await self._send_forbidden(send, exc)
            return

        # Mark request as processed so inner @rate_limit decorator won't double-charge
        request.state._rate_limited_by_middleware = True
        request.state.rate_limit_result = result

        if not result.allowed:
            await self._send_rate_limit_exceeded(request, result, send)
            return

        # Request allowed: forward downstream and inject rate limit headers into response
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start" and self.include_headers:
                raw_headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                rl_headers = build_rate_limit_headers(result, include_retry_after=False)
                for name, value in rl_headers.items():
                    raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
                message["headers"] = raw_headers
            await send(message)

        await self.app(scope, receive, send_with_headers)

    async def _send_rate_limit_exceeded(
        self,
        request: Request,
        result: RateLimitResult,
        send: Send,
    ) -> None:
        """Send standard HTTP 429 Too Many Requests response."""
        status_code = 429
        if self.custom_exceeded_handler is not None:
            status_code, body_data = self.custom_exceeded_handler(request, result)
        else:
            body_data = {
                "error": "Rate limit exceeded",
                "message": (
                    f"Rate limit exceeded: {result.limit} requests permitted. "
                    f"Retry after {result.retry_after}s."
                ),
                "limit": result.limit,
                "remaining": result.remaining,
                "retry_after": result.retry_after,
            }

        body_bytes = json.dumps(body_data).encode("utf-8")
        headers = build_rate_limit_headers(result, include_retry_after=True)
        headers["content-type"] = "application/json"
        headers["content-length"] = str(len(body_bytes))

        raw_headers = [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in headers.items()
        ]

        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": raw_headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body_bytes,
            }
        )

    async def _send_forbidden(self, send: Send, exc: BlacklistedError) -> None:
        """Send HTTP 403 Forbidden for blacklisted identifiers."""
        body_data = {
            "error": "Forbidden",
            "message": exc.message,
            "identifier": exc.identifier,
        }
        body_bytes = json.dumps(body_data).encode("utf-8")
        raw_headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body_bytes)).encode("latin-1")),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": raw_headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body_bytes,
            }
        )
