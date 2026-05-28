"""Tests for TokenManager."""

import pytest
from minos_desktop.security.token_manager import TokenManager


def test_token_persists_across_instances():
    """Token should persist across TokenManager instances."""
    manager1 = TokenManager()
    token1 = manager1.get_or_create_token()

    manager2 = TokenManager()
    token2 = manager2.get_or_create_token()

    assert token1 == token2, "Token should be same across instances"
    assert len(token1) >= 32, "Token should be sufficiently long"


def test_token_is_cryptographically_secure():
    """Generated token should be URL-safe and sufficiently random."""
    manager = TokenManager()
    token = manager.get_or_create_token()

    # URL-safe base64 tokens only contain alphanumeric, -, and _
    assert all(c.isalnum() or c in "-_" for c in token)
    assert len(token) >= 32


def test_regenerate_token_creates_new_token():
    """Regenerating token should create a different token."""
    manager = TokenManager()
    token1 = manager.get_or_create_token()
    token2 = manager.regenerate_token()

    assert token1 != token2, "Regenerated token should be different"

    # Verify new token persists
    manager3 = TokenManager()
    token3 = manager3.get_or_create_token()
    assert token3 == token2, "New token should persist"
