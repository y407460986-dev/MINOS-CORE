"""Tests for SecureAPIKeyStore."""

import pytest
from unittest.mock import patch, MagicMock

from minos_desktop.security import SecureAPIKeyStore, SecretStr


class TestSecureAPIKeyStore:
    """Test SecureAPIKeyStore class."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up test keys after each test."""
        # Clean up before test
        try:
            SecureAPIKeyStore.delete_api_key("test-provider")
            SecureAPIKeyStore.delete_api_key("openai")
            SecureAPIKeyStore.delete_api_key("anthropic")
            SecureAPIKeyStore.delete_api_key("OpenAI")
            SecureAPIKeyStore.delete_api_key("测试提供商")
        except Exception:
            pass

        yield

        # Clean up after test
        try:
            SecureAPIKeyStore.delete_api_key("test-provider")
            SecureAPIKeyStore.delete_api_key("openai")
            SecureAPIKeyStore.delete_api_key("anthropic")
            SecureAPIKeyStore.delete_api_key("OpenAI")
            SecureAPIKeyStore.delete_api_key("测试提供商")
        except Exception:
            pass

    def test_store_api_key_string(self):
        """Test storing API key as string."""
        SecureAPIKeyStore.store_api_key("test-provider", "test-key-123")

        # Verify it was stored
        assert SecureAPIKeyStore.has_api_key("test-provider")

    def test_store_api_key_secret_str(self):
        """Test storing API key as SecretStr."""
        secret = SecretStr("test-key-456")
        SecureAPIKeyStore.store_api_key("test-provider", secret)

        # Verify it was stored
        assert SecureAPIKeyStore.has_api_key("test-provider")

    def test_store_api_key_empty_raises(self):
        """Test storing empty API key raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            SecureAPIKeyStore.store_api_key("test-provider", "")

        with pytest.raises(ValueError, match="cannot be empty"):
            SecureAPIKeyStore.store_api_key("test-provider", SecretStr(""))

    def test_get_api_key_exists(self):
        """Test getting existing API key."""
        SecureAPIKeyStore.store_api_key("test-provider", "test-key-789")

        result = SecureAPIKeyStore.get_api_key("test-provider")

        assert result is not None
        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == "test-key-789"

    def test_get_api_key_not_exists(self):
        """Test getting non-existent API key returns None."""
        result = SecureAPIKeyStore.get_api_key("nonexistent-provider")
        assert result is None

    def test_delete_api_key_exists(self):
        """Test deleting existing API key."""
        SecureAPIKeyStore.store_api_key("test-provider", "test-key")

        # Verify it exists
        assert SecureAPIKeyStore.has_api_key("test-provider")

        # Delete it
        SecureAPIKeyStore.delete_api_key("test-provider")

        # Verify it's gone
        assert not SecureAPIKeyStore.has_api_key("test-provider")

    def test_delete_api_key_not_exists(self):
        """Test deleting non-existent API key doesn't raise."""
        # Should not raise
        SecureAPIKeyStore.delete_api_key("nonexistent-provider")

    def test_has_api_key_true(self):
        """Test has_api_key returns True for existing key."""
        SecureAPIKeyStore.store_api_key("test-provider", "test-key")
        assert SecureAPIKeyStore.has_api_key("test-provider") is True

    def test_has_api_key_false(self):
        """Test has_api_key returns False for non-existent key."""
        assert SecureAPIKeyStore.has_api_key("nonexistent-provider") is False

    def test_list_providers(self):
        """Test list_providers returns empty list (limitation of keyring API)."""
        # Store some keys
        SecureAPIKeyStore.store_api_key("openai", "key1")
        SecureAPIKeyStore.store_api_key("anthropic", "key2")

        # list_providers returns empty list due to keyring API limitation
        result = SecureAPIKeyStore.list_providers()
        assert result == []

    def test_service_name(self):
        """Test service name is correct."""
        assert SecureAPIKeyStore.SERVICE_NAME == "MINOS-Desktop"

    def test_multiple_providers(self):
        """Test storing keys for multiple providers."""
        SecureAPIKeyStore.store_api_key("openai", "openai-key")
        SecureAPIKeyStore.store_api_key("anthropic", "anthropic-key")

        # Both should exist
        assert SecureAPIKeyStore.has_api_key("openai")
        assert SecureAPIKeyStore.has_api_key("anthropic")

        # Get both
        openai_key = SecureAPIKeyStore.get_api_key("openai")
        anthropic_key = SecureAPIKeyStore.get_api_key("anthropic")

        assert openai_key.get_secret_value() == "openai-key"
        assert anthropic_key.get_secret_value() == "anthropic-key"

    def test_update_api_key(self):
        """Test updating existing API key."""
        # Store initial key
        SecureAPIKeyStore.store_api_key("test-provider", "old-key")

        # Update with new key
        SecureAPIKeyStore.store_api_key("test-provider", "new-key")

        # Verify new key is stored
        result = SecureAPIKeyStore.get_api_key("test-provider")
        assert result.get_secret_value() == "new-key"

    def test_provider_name_case_sensitive(self):
        """Test provider names are case-sensitive."""
        SecureAPIKeyStore.store_api_key("OpenAI", "key1")
        SecureAPIKeyStore.store_api_key("openai", "key2")

        # Should be different keys
        key1 = SecureAPIKeyStore.get_api_key("OpenAI")
        key2 = SecureAPIKeyStore.get_api_key("openai")

        assert key1.get_secret_value() == "key1"
        assert key2.get_secret_value() == "key2"

    def test_unicode_provider_name(self):
        """Test storing key with unicode provider name."""
        SecureAPIKeyStore.store_api_key("测试提供商", "test-key")

        result = SecureAPIKeyStore.get_api_key("测试提供商")
        assert result.get_secret_value() == "test-key"

    def test_special_characters_in_key(self):
        """Test storing key with special characters."""
        special_key = "sk-proj-abc123!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        SecureAPIKeyStore.store_api_key("test-provider", special_key)

        result = SecureAPIKeyStore.get_api_key("test-provider")
        assert result.get_secret_value() == special_key

    def test_long_api_key(self):
        """Test storing reasonably long API key."""
        # Windows Credential Manager has a limit of ~2560 bytes total
        # (including service name, username, and password)
        # Use a reasonable long key that fits within the limit
        long_key = "x" * 1000
        SecureAPIKeyStore.store_api_key("test-provider", long_key)

        result = SecureAPIKeyStore.get_api_key("test-provider")
        assert result.get_secret_value() == long_key

    @patch("keyring.set_password")
    def test_keyring_set_password_called(self, mock_set_password):
        """Test that keyring.set_password is called correctly."""
        SecureAPIKeyStore.store_api_key("test-provider", "test-key")

        mock_set_password.assert_called_once_with(
            "MINOS-Desktop", "test-provider", "test-key"
        )

    @patch("keyring.get_password")
    def test_keyring_get_password_called(self, mock_get_password):
        """Test that keyring.get_password is called correctly."""
        mock_get_password.return_value = "test-key"

        result = SecureAPIKeyStore.get_api_key("test-provider")

        mock_get_password.assert_called_once_with("MINOS-Desktop", "test-provider")
        assert result.get_secret_value() == "test-key"

    @patch("keyring.delete_password")
    def test_keyring_delete_password_called(self, mock_delete_password):
        """Test that keyring.delete_password is called correctly."""
        SecureAPIKeyStore.delete_api_key("test-provider")

        mock_delete_password.assert_called_once_with("MINOS-Desktop", "test-provider")

    @patch("keyring.get_password")
    def test_get_api_key_none_from_keyring(self, mock_get_password):
        """Test getting API key when keyring returns None."""
        mock_get_password.return_value = None

        result = SecureAPIKeyStore.get_api_key("test-provider")

        assert result is None

    @patch("keyring.delete_password")
    def test_delete_api_key_exception_ignored(self, mock_delete_password):
        """Test that exceptions during delete are ignored."""
        mock_delete_password.side_effect = Exception("Keyring error")

        # Should not raise
        SecureAPIKeyStore.delete_api_key("test-provider")
