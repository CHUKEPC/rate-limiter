"""Header and API key based key extraction strategies.

Extracts rate limiting keys from HTTP request headers (such as Authorization,
X-API-Key, or custom tokens) or query string parameters.
"""

from typing import Any

from rate_limiter.exceptions import KeyExtractionError
from rate_limiter.keys.base import BaseKeyStrategy


class HeaderKeyStrategy(BaseKeyStrategy):
    """Extracts rate limit key from a specific HTTP request header."""

    def __init__(
        self,
        header_name: str,
        prefix: str | None = None,
        fallback: str | None = None,
    ) -> None:
        """Initialize HeaderKeyStrategy.

        Args:
            header_name: Header key name (e.g. 'X-API-Key', 'Authorization').
            prefix: Custom prefix to prepend to extracted key (e.g. 'hdr:').
            fallback: Default value if header is absent.
        """
        self.header_name = header_name.lower()
        self.prefix = prefix or f"hdr:{self.header_name}:"
        self.fallback = fallback

    async def extract(self, request: Any) -> str:
        """Extract header value from request.

        Args:
            request: Incoming HTTP request.

        Returns:
            Normalized prefixed key string.

        Raises:
            KeyExtractionError: If header is missing and no fallback is set.
        """
        headers = getattr(request, "headers", None)
        val: str | None = None

        if headers is not None:
            val = headers.get(self.header_name)

        if not val and hasattr(request, "META"):
            # Django headers are prefixed with HTTP_
            django_hdr = "HTTP_" + self.header_name.upper().replace("-", "_")
            val = request.META.get(django_hdr)

        if not val:
            if self.fallback is not None:
                val = self.fallback
            else:
                raise KeyExtractionError(
                    strategy_name="HeaderKeyStrategy",
                    reason=f"Required header '{self.header_name}' was not present",
                    request_info=request,
                )

        return f"{self.prefix}{val.strip()}"


class ApiKeyStrategy(BaseKeyStrategy):
    """Extracts API key from standard headers or query parameters."""

    def __init__(
        self,
        header_names: list[str] | None = None,
        query_param_names: list[str] | None = None,
        fallback: str | None = None,
    ) -> None:
        """Initialize ApiKeyStrategy.

        Args:
            header_names: Headers to check in priority order.
            query_param_names: Query parameters to check if headers are absent.
            fallback: Default API key if none found.
        """
        self.header_names = header_names or ["x-api-key", "api-key", "apikey"]
        self.query_param_names = query_param_names or ["api_key", "apikey", "key"]
        self.fallback = fallback

    async def extract(self, request: Any) -> str:
        """Extract API key from header or query parameter."""
        api_key: str | None = None

        # Check headers
        headers = getattr(request, "headers", None)
        if headers is not None:
            for h in self.header_names:
                candidate = headers.get(h)
                if candidate:
                    api_key = candidate.strip()
                    break

        # Check query parameters if not found in headers
        if not api_key:
            query_params = getattr(request, "query_params", None)
            if query_params is not None:
                for q in self.query_param_names:
                    candidate = query_params.get(q)
                    if candidate:
                        api_key = candidate.strip()
                        break

            # Handle Django GET query params
            get_params = getattr(request, "GET", None)
            if not api_key and get_params is not None:
                for q in self.query_param_names:
                    candidate = get_params.get(q)
                    if candidate:
                        api_key = str(candidate).strip()
                        break

        if not api_key:
            if self.fallback is not None:
                api_key = self.fallback
            else:
                raise KeyExtractionError(
                    strategy_name="ApiKeyStrategy",
                    reason="No API key found in headers or query parameters",
                    request_info=request,
                )

        return f"apikey:{api_key}"
