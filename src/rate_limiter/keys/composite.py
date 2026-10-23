"""Composite and custom key extraction strategies.

Allows composing multiple key strategies into a multi-dimensional key
(e.g., combining User ID and Route, or IP and User Tier), as well as
wrapping custom arbitrary callable extraction functions.
"""

import inspect
from collections.abc import Callable
from typing import Any

from rate_limiter.keys.base import BaseKeyStrategy


class CompositeKeyStrategy(BaseKeyStrategy):
    """Combines multiple key strategies into a single composite delimiter-separated key."""

    def __init__(
        self,
        strategies: list[BaseKeyStrategy],
        delimiter: str = ":",
        prefix: str = "comp:",
    ) -> None:
        """Initialize CompositeKeyStrategy.

        Args:
            strategies: List of key strategies executed in order.
            delimiter: Separator between key components.
            prefix: Prefix for the resulting composite key.
        """
        self.strategies = strategies
        self.delimiter = delimiter
        self.prefix = prefix

    async def extract(self, request: Any) -> str:
        """Extract parts from each strategy and join them."""
        parts: list[str] = []
        for strategy in self.strategies:
            part = await strategy.extract(request)
            parts.append(part)
        return f"{self.prefix}{self.delimiter.join(parts)}"


class CustomKeyStrategy(BaseKeyStrategy):
    """Wraps a custom sync or async callable to extract a rate limit key."""

    def __init__(
        self,
        extractor: Callable[[Any], Any],
        prefix: str = "custom:",
    ) -> None:
        """Initialize CustomKeyStrategy.

        Args:
            extractor: Sync or async callable accepting request and returning str.
            prefix: Prefix to prepend to extracted key.
        """
        self.extractor = extractor
        self.prefix = prefix

    async def extract(self, request: Any) -> str:
        """Execute the custom callable and normalize the output string."""
        if inspect.iscoroutinefunction(self.extractor):
            val = await self.extractor(request)
        else:
            val = self.extractor(request)

        return f"{self.prefix}{str(val).strip()}"
