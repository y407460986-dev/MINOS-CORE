"""Tests for authentication with TokenManager."""

import pytest

from minos_desktop.api.auth import _token_manager, require_api_token
from minos_desktop.api.schemas import APIError


def test_require_api_token_with_valid_token():
    """Valid token should pass authentication."""
    token = _token_manager.get_or_create_token()
    authorization = f"Bearer {token}"

    # Should not raise
    require_api_token(authorization)


def test_require_api_token_missing_header():
    """Missing Authorization header should raise 401."""
    with pytest.raises(APIError) as exc_info:
        require_api_token(None)

    assert exc_info.value.status_code == 401
    assert "Missing Authorization header" in exc_info.value.detail


def test_require_api_token_invalid_format():
    """Invalid Authorization header format should raise 401."""
    with pytest.raises(APIError) as exc_info:
        require_api_token("InvalidFormat token123")

    assert exc_info.value.status_code == 401
    assert "Invalid Authorization header format" in exc_info.value.detail


def test_require_api_token_wrong_token():
    """Wrong token should raise 401."""
    with pytest.raises(APIError) as exc_info:
        require_api_token("Bearer wrong_token_here")

    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


def test_require_api_token_empty_bearer():
    """Empty Bearer token should raise 401."""
    with pytest.raises(APIError) as exc_info:
        require_api_token("Bearer ")

    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail
