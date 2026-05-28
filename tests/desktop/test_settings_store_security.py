"""Security tests for settings store - API key storage in keyring."""

import pytest
from pathlib import Path

from minos_desktop.services.settings_store import DesktopSettingsStore
from minos_desktop.security.secret_str import SecretStr
from minos_desktop.security.api_key_store import SecureAPIKeyStore


def test_api_key_stored_in_keyring_not_sqlite(tmp_path: Path) -> None:
    """API keys should be stored in system keyring, not SQLite database."""
    store = DesktopSettingsStore(db_path=tmp_path / "test.db")

    # Store API key
    store.set_ai_overrides(api_key=SecretStr("sk-test-key-12345"))

    # Verify: SQLite should NOT contain the actual key
    raw_value = store._get("ai_api_key")
    assert raw_value == "", "API key should not be in SQLite"

    # Verify: Flag should be set
    assert store._get("ai_api_key_configured") == "true"

    # Verify: Key can be retrieved
    overrides = store.get_ai_overrides()
    assert overrides["api_key"] == "sk-test-key-12345"

    # Cleanup
    SecureAPIKeyStore.delete_api_key("openai")


def test_api_key_with_plain_string(tmp_path: Path) -> None:
    """API key storage should work with plain string (backward compatibility)."""
    store = DesktopSettingsStore(db_path=tmp_path / "test.db")

    # Store API key as plain string
    store.set_ai_overrides(api_key="sk-plain-string-key")

    # Verify: Key can be retrieved
    overrides = store.get_ai_overrides()
    assert overrides["api_key"] == "sk-plain-string-key"

    # Cleanup
    SecureAPIKeyStore.delete_api_key("openai")


def test_api_key_retrieval_when_not_configured(tmp_path: Path) -> None:
    """When no API key is configured, should return None."""
    store = DesktopSettingsStore(db_path=tmp_path / "test.db")

    # Don't set any API key
    overrides = store.get_ai_overrides()

    # Should return None for api_key
    assert overrides["api_key"] is None


def test_api_key_update_replaces_old_key(tmp_path: Path) -> None:
    """Updating API key should replace the old one in keyring."""
    store = DesktopSettingsStore(db_path=tmp_path / "test.db")

    # Store first key
    store.set_ai_overrides(api_key="sk-old-key")

    # Update with new key
    store.set_ai_overrides(api_key=SecretStr("sk-new-key"))

    # Verify: New key is retrieved
    overrides = store.get_ai_overrides()
    assert overrides["api_key"] == "sk-new-key"

    # Cleanup
    SecureAPIKeyStore.delete_api_key("openai")


def test_other_overrides_still_work(tmp_path: Path) -> None:
    """Model and base_url should still be stored in SQLite."""
    store = DesktopSettingsStore(db_path=tmp_path / "test.db")

    # Set all overrides
    store.set_ai_overrides(
        model="gpt-4",
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("sk-test-key")
    )

    # Verify: Model and base_url are in SQLite
    assert store._get("ai_model") == "gpt-4"
    assert store._get("ai_base_url") == "https://api.openai.com/v1"

    # Verify: All overrides can be retrieved
    overrides = store.get_ai_overrides()
    assert overrides["model"] == "gpt-4"
    assert overrides["base_url"] == "https://api.openai.com/v1"
    assert overrides["api_key"] == "sk-test-key"

    # Cleanup
    SecureAPIKeyStore.delete_api_key("openai")


def test_api_key_flag_not_set_on_storage_failure(tmp_path: Path) -> None:
    """If keyring storage fails, the configured flag should NOT be set."""
    store = DesktopSettingsStore(db_path=tmp_path / "test.db")

    # Try to store empty API key (should raise ValueError)
    with pytest.raises(ValueError, match="API key cannot be empty"):
        store.set_ai_overrides(api_key="")

    # Verify: Flag should NOT be set
    assert store._get("ai_api_key_configured") == ""

    # Verify: No key in keyring
    assert SecureAPIKeyStore.get_api_key("openai") is None
