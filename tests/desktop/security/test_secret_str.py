"""Tests for SecretStr."""

import pytest
from pydantic import BaseModel

from minos_desktop.security import SecretStr


class TestSecretStr:
    """Test SecretStr class."""

    def test_init_with_string(self):
        """Test initializing SecretStr with a string."""
        secret = SecretStr("my-secret-key")
        assert secret.get_secret_value() == "my-secret-key"

    def test_init_with_non_string(self):
        """Test initializing SecretStr with non-string raises TypeError."""
        with pytest.raises(TypeError, match="requires str"):
            SecretStr(123)

        with pytest.raises(TypeError, match="requires str"):
            SecretStr(None)

    def test_get_secret_value(self):
        """Test getting the secret value."""
        secret = SecretStr("my-secret")
        assert secret.get_secret_value() == "my-secret"

    def test_repr_hides_secret(self):
        """Test repr() hides the secret value."""
        secret = SecretStr("my-secret-key")
        assert "my-secret-key" not in repr(secret)
        assert "**********" in repr(secret)
        assert repr(secret) == "SecretStr('**********')"

    def test_str_hides_secret(self):
        """Test str() hides the secret value."""
        secret = SecretStr("my-secret-key")
        assert str(secret) == "**********"
        assert "my-secret-key" not in str(secret)

    def test_equality_same_secret(self):
        """Test equality with same secret."""
        secret1 = SecretStr("same-secret")
        secret2 = SecretStr("same-secret")
        assert secret1 == secret2

    def test_equality_different_secret(self):
        """Test equality with different secret."""
        secret1 = SecretStr("secret1")
        secret2 = SecretStr("secret2")
        assert secret1 != secret2

    def test_equality_with_non_secret_str(self):
        """Test equality with non-SecretStr object."""
        secret = SecretStr("my-secret")
        assert secret != "my-secret"
        assert secret != 123
        assert secret is not None

    def test_hash(self):
        """Test hashing SecretStr."""
        secret1 = SecretStr("same-secret")
        secret2 = SecretStr("same-secret")
        secret3 = SecretStr("different-secret")

        # Same secrets should have same hash
        assert hash(secret1) == hash(secret2)

        # Different secrets should (likely) have different hash
        assert hash(secret1) != hash(secret3)

    def test_hash_in_set(self):
        """Test using SecretStr in a set."""
        secret1 = SecretStr("secret1")
        secret2 = SecretStr("secret1")
        secret3 = SecretStr("secret2")

        secret_set = {secret1, secret2, secret3}

        # Should only have 2 unique secrets
        assert len(secret_set) == 2

    def test_hash_in_dict(self):
        """Test using SecretStr as dict key."""
        secret1 = SecretStr("key1")
        secret2 = SecretStr("key1")
        secret3 = SecretStr("key2")

        secret_dict = {secret1: "value1", secret3: "value2"}

        # Should be able to access with equivalent SecretStr
        assert secret_dict[secret2] == "value1"
        assert len(secret_dict) == 2

    def test_len(self):
        """Test getting length of secret."""
        secret = SecretStr("12345")
        assert len(secret) == 5

        empty_secret = SecretStr("")
        assert len(empty_secret) == 0

    def test_bool_non_empty(self):
        """Test bool() with non-empty secret."""
        secret = SecretStr("my-secret")
        assert bool(secret) is True

    def test_bool_empty(self):
        """Test bool() with empty secret."""
        empty_secret = SecretStr("")
        assert bool(empty_secret) is False

    def test_secret_not_leaked_in_exception(self):
        """Test that secret is not leaked in exception messages."""
        secret = SecretStr("super-secret-key")

        # Create an exception that includes the SecretStr
        try:
            raise ValueError(f"Invalid secret: {secret}")
        except ValueError as e:
            error_message = str(e)
            assert "super-secret-key" not in error_message
            assert "**********" in error_message

    def test_secret_not_leaked_in_logging(self, caplog):
        """Test that secret is not leaked in log messages."""
        import logging

        secret = SecretStr("secret-api-key")

        # Log the secret with explicit logger
        logger = logging.getLogger(__name__)
        logger.info(f"API key: {secret}")

        # Check log output
        assert "secret-api-key" not in caplog.text
        # The secret should be masked in string representation
        assert str(secret) == "**********"

    def test_immutability(self):
        """Test that SecretStr protects the secret value."""
        secret = SecretStr("my-secret")

        # The secret value should only be accessible via get_secret_value()
        assert secret.get_secret_value() == "my-secret"

        # String representation should hide the secret
        assert str(secret) == "**********"
        assert repr(secret) == "SecretStr('**********')"

    def test_empty_string(self):
        """Test SecretStr with empty string."""
        secret = SecretStr("")
        assert secret.get_secret_value() == ""
        assert len(secret) == 0
        assert not secret

    def test_whitespace_string(self):
        """Test SecretStr with whitespace."""
        secret = SecretStr("   ")
        assert secret.get_secret_value() == "   "
        assert len(secret) == 3
        assert bool(secret) is True

    def test_unicode_secret(self):
        """Test SecretStr with unicode characters."""
        secret = SecretStr("密钥🔑")
        assert secret.get_secret_value() == "密钥🔑"
        assert "密钥" not in str(secret)
        assert "🔑" not in repr(secret)

    def test_multiline_secret(self):
        """Test SecretStr with multiline string."""
        multiline = "line1\nline2\nline3"
        secret = SecretStr(multiline)
        assert secret.get_secret_value() == multiline
        assert "line1" not in str(secret)
        assert "line2" not in repr(secret)

    def test_pydantic_model_dump_masks_secret_but_get_secret_value_still_works(self):
        class Config(BaseModel):
            api_key: SecretStr

        config = Config(api_key="secret-from-ui")

        dumped = config.model_dump()
        dumped_json = config.model_dump_json()

        assert config.api_key.get_secret_value() == "secret-from-ui"
        assert dumped["api_key"] == "**********"
        assert "secret-from-ui" not in dumped_json
        assert "**********" in dumped_json
