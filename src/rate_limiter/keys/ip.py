"""IP address based rate limiting key extraction strategy.

Inspects standard proxy headers (X-Forwarded-For, X-Real-IP, CF-Connecting-IP)
and native socket remote addresses to determine the true client IP address.
"""

from typing import Any

from rate_limiter.exceptions import KeyExtractionError
from rate_limiter.keys.base import BaseKeyStrategy


class IPKeyStrategy(BaseKeyStrategy):
    """Extracts client IP address from HTTP headers or request socket."""

    def __init__(
        self,
        trusted_proxies: set[str] | None = None,
        fallback: str | None = "127.0.0.1",
        header_names: list[str] | None = None,
    ) -> None:
        """Initialize the IP key strategy.

        Args:
            trusted_proxies: Optional set of proxy IPs trusted to provide forwarding headers.
            fallback: Default IP string if client address cannot be determined.
            header_names: Custom list of header names to inspect in order of priority.
        """
        self.trusted_proxies = trusted_proxies or set()
        self.fallback = fallback
        self.header_names = header_names or [
            "cf-connecting-ip",
            "x-real-ip",
            "x-forwarded-for",
            "fastly-client-ip",
        ]

    async def extract(self, request: Any) -> str:
        """Extract client IP address from the request.

        Args:
            request: FastAPI/Starlette or Django request.

        Returns:
            Normalized client IP address string prefixed with 'ip:'.

        Raises:
            KeyExtractionError: If IP cannot be resolved and no fallback was set.
        """
        ip: str | None = None

        # Handle Starlette / FastAPI Request
        headers = getattr(request, "headers", None)
        if headers is not None:
            for header in self.header_names:
                val = headers.get(header)
                if val:
                    # In X-Forwarded-For: "client, proxy1, proxy2"
                    candidate = val.split(",")[0].strip()
                    if candidate:
                        ip = candidate
                        break

            if not ip and hasattr(request, "client") and request.client:
                ip = getattr(request.client, "host", None)

        # Handle Django Request
        meta = getattr(request, "META", None)
        if not ip and meta is not None:
            xff = meta.get("HTTP_X_FORWARDED_FOR")
            if xff:
                ip = xff.split(",")[0].strip()
            elif meta.get("HTTP_X_REAL_IP"):
                ip = meta.get("HTTP_X_REAL_IP")
            elif meta.get("REMOTE_ADDR"):
                ip = meta.get("REMOTE_ADDR")

        if not ip:
            if self.fallback:
                ip = self.fallback
            else:
                raise KeyExtractionError(
                    strategy_name="IPKeyStrategy",
                    reason="Could not determine client IP address from request",
                    request_info=request,
                )

        return f"ip:{ip.strip()}"
