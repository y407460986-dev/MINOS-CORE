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


def test_get_or_create_token_handles_keyring_failure(monkeypatch):
    """Should raise clear error when keyring is unavailable."""
    from minos_desktop.security.api_key_store import SecureAPIKeyStore

    def mock_get_api_key(*args, **kwargs):
        raise RuntimeError("Keyring unavailable")

    monkeypatch.setattr(SecureAPIKeyStore, "get_api_key", mock_get_api_key)

    manager = TokenManager()
    with pytest.raises(RuntimeError, match="Failed to access system keyring"):
        manager.get_or_create_token()


def test_get_or_create_token_generates_and_stores_when_missing(monkeypatch):
    manager = TokenManager()
    stored = {}
    monkeypatch.setattr(manager.keystore, "get_api_key", lambda _provider: None)
    monkeypatch.setattr(
        manager.keystore,
        "store_api_key",
        lambda provider, token: stored.update(provider=provider, token=token),
    )
    monkeypatch.setattr("minos_desktop.security.token_manager.secrets.token_urlsafe", lambda _length: "new-token")

    assert manager.get_or_create_token() == "new-token"
    assert stored == {"provider": TokenManager.TOKEN_PROVIDER, "token": "new-token"}


def test_regenerate_token_handles_keyring_failure(monkeypatch):
    manager = TokenManager()
    monkeypatch.setattr(
        manager.keystore,
        "store_api_key",
        lambda _provider, _token: (_ for _ in ()).throw(RuntimeError("locked")),
    )

    with pytest.raises(RuntimeError, match="Failed to store token in keyring") as exc_info:
        manager.regenerate_token()
    assert isinstance(exc_info.value.__cause__, RuntimeError)
