"""Abstract base class for key extraction strategies.

Key strategies inspect incoming HTTP requests (FastAPI/Starlette or Django) and
extract a unique string identifier representing the client (e.g., IP address, user ID).
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseKeyStrategy(ABC):
    """Abstract strategy for extracting rate limit partition keys from requests."""

    @abstractmethod
    async def extract(self, request: Any) -> str:
        """Extract a rate limit identifier key from the request.

        Args:
            request: The incoming HTTP request object (e.g., Starlette/FastAPI Request).

        Returns:
            Extracted partition key string.

        Raises:
            KeyExtractionError: If key cannot be identified and no default fallback exists.
        """
        pass
