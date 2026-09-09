"""API authentication middleware for FastAPI."""

import secrets
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class AuthMiddleware:
    """
    Token-based authentication middleware for FastAPI.

    Supports Bearer token authentication.
    """

    def __init__(self, token: str | None = None):
        """
        Initialize authentication middleware.

        Args:
            token: Authentication token. If None, a random token is generated.
        """
        self.token = token or self._generate_token()
        self.security = HTTPBearer()

    @staticmethod
    def _generate_token(length: int = 32) -> str:
        """
        Generate a secure random token.

        Args:
            length: Token length in bytes

        Returns:
            Hex-encoded token
        """
        return secrets.token_hex(length)

    def get_token(self) -> str:
        """
        Get the current authentication token.

        Returns:
            Authentication token
        """
        return self.token

    async def verify_token(
        self, credentials: HTTPAuthorizationCredentials
    ) -> bool:
        """
        Verify authentication token.

        Args:
            credentials: HTTP authorization credentials

        Returns:
            True if token is valid, False otherwise
        """
        if not credentials:
            return False

        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(credentials.credentials, self.token)

    async def __call__(self, request: Request) -> None:
        """
        Middleware callable for FastAPI.

        Args:
            request: FastAPI request

        Raises:
            HTTPException: If authentication fails
        """
        # Extract authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Parse Bearer token
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = parts[1]

        # Verify token using constant-time comparison
        if not secrets.compare_digest(token, self.token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )


RouteHandler = Callable[..., Awaitable[Any]]


def require_auth(auth: AuthMiddleware) -> Callable[[RouteHandler], RouteHandler]:
    """
    Decorator to require authentication for a route.

    Args:
        auth: AuthMiddleware instance

    Returns:
        Decorator function

    Example:
        ```python
        auth = AuthMiddleware()

        @app.get("/protected")
        @require_auth(auth)
        async def protected_route(request: Request):
            return {"message": "Protected data"}
        ```
    """

    def decorator(func: RouteHandler) -> RouteHandler:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract request from kwargs
            request = kwargs.get("request")
            if not request:
                # Try to find request in args
                for arg in args:
                    # Use duck typing to check for Request-like object
                    if hasattr(arg, 'headers') and hasattr(arg.headers, 'get'):
                        request = arg
                        break

            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found",
                )

            # Verify authentication
            await auth(request)

            # Call original function
            return await func(*args, **kwargs)

        return wrapper

    return decorator
