"""User ID based key extraction strategy.

Extracts authenticated user identifiers from request state, session,
or authentication middleware context (e.g. request.state.user or request.user).
"""

from typing import Any

from rate_limiter.exceptions import KeyExtractionError
from rate_limiter.keys.base import BaseKeyStrategy


class UserKeyStrategy(BaseKeyStrategy):
    """Extracts authenticated user identifier from request object."""

    def __init__(
        self,
        user_attribute: str = "id",
        fallback_to_anonymous: bool = True,
        anonymous_identifier: str = "anonymous",
    ) -> None:
        """Initialize UserKeyStrategy.

        Args:
            user_attribute: Attribute or dictionary key to retrieve from the user object.
            fallback_to_anonymous: If True, returns anonymous identifier when user is not logged in.
            anonymous_identifier: Identifier string used for unauthenticated visitors.
        """
        self.user_attribute = user_attribute
        self.fallback_to_anonymous = fallback_to_anonymous
        self.anonymous_identifier = anonymous_identifier

    async def extract(self, request: Any) -> str:
        """Extract user identifier from request state or user object."""
        user_obj: Any = None

        # Check Starlette request.state.user
        state = getattr(request, "state", None)
        if state is not None and hasattr(state, "user"):
            user_obj = state.user

        # Check request.user (Starlette / Django)
        if user_obj is None and hasattr(request, "user"):
            user_obj = request.user

        uid: str | None = None
        if user_obj is not None:
            # Check if user is authenticated (e.g. Django is_authenticated)
            is_auth = getattr(user_obj, "is_authenticated", True)
            if callable(is_auth):
                is_auth = is_auth()

            if is_auth:
                if isinstance(user_obj, dict):
                    raw_val = user_obj.get(self.user_attribute)
                else:
                    raw_val = getattr(user_obj, self.user_attribute, None)

                if raw_val is not None:
                    uid = str(raw_val).strip()

        if uid:
            return f"user:{uid}"

        if self.fallback_to_anonymous:
            return f"user:{self.anonymous_identifier}"

        raise KeyExtractionError(
            strategy_name="UserKeyStrategy",
            reason="Authenticated user not found on request",
            request_info=request,
        )
