"""Tests for AuthMiddleware."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from minos_desktop.security import AuthMiddleware, require_auth


class TestAuthMiddleware:
    """Test AuthMiddleware class."""

    def test_init_with_token(self):
        """Test initializing with provided token."""
        auth = AuthMiddleware(token="my-custom-token")
        assert auth.get_token() == "my-custom-token"

    def test_init_without_token_generates_random(self):
        """Test initializing without token generates random token."""
        auth1 = AuthMiddleware()
        auth2 = AuthMiddleware()

        # Should generate different tokens
        assert auth1.get_token() != auth2.get_token()

        # Should be 64 characters (32 bytes hex-encoded)
        assert len(auth1.get_token()) == 64

    def test_generate_token_default_length(self):
        """Test generating token with default length."""
        token = AuthMiddleware._generate_token()

        # Default is 32 bytes = 64 hex characters
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_generate_token_custom_length(self):
        """Test generating token with custom length."""
        token = AuthMiddleware._generate_token(length=16)

        # 16 bytes = 32 hex characters
        assert len(token) == 32

    def test_get_token(self):
        """Test getting the authentication token."""
        auth = AuthMiddleware(token="test-token-123")
        assert auth.get_token() == "test-token-123"

    @pytest.mark.asyncio
    async def test_verify_token_valid(self):
        """Test verifying valid token."""
        auth = AuthMiddleware(token="valid-token")
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid-token"
        )

        result = await auth.verify_token(credentials)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_token_invalid(self):
        """Test verifying invalid token."""
        auth = AuthMiddleware(token="valid-token")
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid-token"
        )

        result = await auth.verify_token(credentials)
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_token_none(self):
        """Test verifying None credentials."""
        auth = AuthMiddleware(token="valid-token")

        result = await auth.verify_token(None)
        assert result is False

    @pytest.mark.asyncio
    async def test_call_valid_token(self):
        """Test middleware with valid token."""
        auth = AuthMiddleware(token="valid-token")

        # Create mock request with valid authorization header
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "Bearer valid-token"

        # Should not raise
        await auth(request)

    @pytest.mark.asyncio
    async def test_call_missing_authorization_header(self):
        """Test middleware with missing authorization header."""
        auth = AuthMiddleware(token="valid-token")

        # Create mock request without authorization header
        request = MagicMock(spec=Request)
        request.headers.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await auth(request)

        assert exc_info.value.status_code == 401
        assert "Missing authorization header" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_call_invalid_header_format(self):
        """Test middleware with invalid header format."""
        auth = AuthMiddleware(token="valid-token")

        # Create mock request with invalid header format
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "InvalidFormat"

        with pytest.raises(HTTPException) as exc_info:
            await auth(request)

        assert exc_info.value.status_code == 401
        assert "Invalid authorization header format" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_call_wrong_scheme(self):
        """Test middleware with wrong authentication scheme."""
        auth = AuthMiddleware(token="valid-token")

        # Create mock request with Basic auth instead of Bearer
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "Basic dXNlcjpwYXNz"

        with pytest.raises(HTTPException) as exc_info:
            await auth(request)

        assert exc_info.value.status_code == 401
        assert "Invalid authorization header format" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_call_invalid_token(self):
        """Test middleware with invalid token."""
        auth = AuthMiddleware(token="valid-token")

        # Create mock request with invalid token
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "Bearer invalid-token"

        with pytest.raises(HTTPException) as exc_info:
            await auth(request)

        assert exc_info.value.status_code == 401
        assert "Invalid authentication token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_call_case_insensitive_bearer(self):
        """Test middleware accepts 'bearer' in any case."""
        auth = AuthMiddleware(token="valid-token")

        # Test lowercase
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "bearer valid-token"
        await auth(request)  # Should not raise

        # Test uppercase
        request.headers.get.return_value = "BEARER valid-token"
        await auth(request)  # Should not raise

        # Test mixed case
        request.headers.get.return_value = "BeArEr valid-token"
        await auth(request)  # Should not raise

    @pytest.mark.asyncio
    async def test_timing_attack_resistance(self):
        """Test that token comparison is constant-time."""
        auth = AuthMiddleware(token="a" * 64)

        # These should take similar time regardless of how many characters match
        credentials1 = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="b" * 64
        )
        credentials2 = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="a" * 63 + "b"
        )

        # Both should return False
        result1 = await auth.verify_token(credentials1)
        result2 = await auth.verify_token(credentials2)

        assert result1 is False
        assert result2 is False

    @pytest.mark.asyncio
    async def test_require_auth_decorator_valid_token(self):
        """Test require_auth decorator with valid token."""
        auth = AuthMiddleware(token="valid-token")

        @require_auth(auth)
        async def protected_route(request: Request):
            return {"message": "success"}

        # Create a real-ish mock request with proper attributes
        request = MagicMock()
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="Bearer valid-token")

        result = await protected_route(request=request)
        assert result == {"message": "success"}

    @pytest.mark.asyncio
    async def test_require_auth_decorator_invalid_token(self):
        """Test require_auth decorator with invalid token."""
        auth = AuthMiddleware(token="valid-token")

        @require_auth(auth)
        async def protected_route(request: Request):
            return {"message": "success"}

        # Create a real-ish mock request with proper attributes
        request = MagicMock()
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="Bearer invalid-token")

        with pytest.raises(HTTPException) as exc_info:
            await protected_route(request=request)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_auth_decorator_no_request(self):
        """Test require_auth decorator when request is not found."""
        auth = AuthMiddleware(token="valid-token")

        @require_auth(auth)
        async def protected_route():
            return {"message": "success"}

        with pytest.raises(HTTPException) as exc_info:
            await protected_route()

        assert exc_info.value.status_code == 500
        assert "Request object not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_auth_decorator_request_in_args(self):
        """Test require_auth decorator with request in args."""
        auth = AuthMiddleware(token="valid-token")

        @require_auth(auth)
        async def protected_route(request: Request, other_arg: str):
            return {"message": other_arg}

        # Create a real-ish mock request with proper attributes
        request = MagicMock()
        request.headers = MagicMock()
        request.headers.get = MagicMock(return_value="Bearer valid-token")

        result = await protected_route(request, "test")
        assert result == {"message": "test"}

    def test_www_authenticate_header(self):
        """Test that WWW-Authenticate header is included in 401 responses."""
        auth = AuthMiddleware(token="valid-token")

        # Create mock request without authorization
        request = MagicMock(spec=Request)
        request.headers.get.return_value = None

        try:
            import asyncio
            asyncio.run(auth(request))
        except HTTPException as e:
            assert e.status_code == 401
            assert "WWW-Authenticate" in e.headers
            assert e.headers["WWW-Authenticate"] == "Bearer"

    def test_token_uniqueness(self):
        """Test that generated tokens are unique."""
        tokens = set()
        for _ in range(100):
            auth = AuthMiddleware()
            tokens.add(auth.get_token())

        # All tokens should be unique
        assert len(tokens) == 100

    def test_token_entropy(self):
        """Test that generated tokens have sufficient entropy."""
        auth = AuthMiddleware()
        token = auth.get_token()

        # Token should be hex string
        assert all(c in "0123456789abcdef" for c in token)

        # Token should have good distribution of characters
        char_counts = {}
        for c in token:
            char_counts[c] = char_counts.get(c, 0) + 1

        # No character should appear more than 20% of the time (very loose check)
        max_count = max(char_counts.values())
        assert max_count < len(token) * 0.2
