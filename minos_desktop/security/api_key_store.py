"""Secure API key storage using system keyring."""


from contextlib import suppress

import keyring

from .secret_str import SecretStr


class SecureAPIKeyStore:
    """
    Secure storage for API keys using the system keyring.

    Uses the operating system's credential storage:
    - Windows: Windows Credential Manager
    - macOS: Keychain
    - Linux: Secret Service API (GNOME Keyring, KWallet)
    """

    SERVICE_NAME = "MINOS-Desktop"

    @classmethod
    def store_api_key(cls, provider: str, api_key: str | SecretStr) -> None:
        """
        Store an API key securely.

        Args:
            provider: Provider name (e.g., "openai", "anthropic")
            api_key: API key to store (string or SecretStr)
        """
        key_value = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key

        if not key_value:
            raise ValueError("API key cannot be empty")

        keyring.set_password(cls.SERVICE_NAME, provider, key_value)

    @classmethod
    def get_api_key(cls, provider: str) -> SecretStr | None:
        """
        Retrieve an API key securely.

        Args:
            provider: Provider name (e.g., "openai", "anthropic")

        Returns:
            SecretStr containing the API key, or None if not found
        """
        key_value = keyring.get_password(cls.SERVICE_NAME, provider)

        if key_value is None:
            return None

        return SecretStr(key_value)

    @classmethod
    def delete_api_key(cls, provider: str) -> None:
        """
        Delete an API key from secure storage.

        Args:
            provider: Provider name (e.g., "openai", "anthropic")
        """
        with suppress(Exception):
            keyring.delete_password(cls.SERVICE_NAME, provider)

    @classmethod
    def list_providers(cls) -> list[str]:
        """
        List all providers with stored API keys.

        Note: This functionality depends on the keyring backend.
        Some backends may not support listing credentials.

        Returns:
            List of provider names
        """
        # Note: keyring doesn't provide a standard way to list all keys
        # This is a limitation of the keyring API
        # We return an empty list and document this limitation
        return []

    @classmethod
    def has_api_key(cls, provider: str) -> bool:
        """
        Check if an API key exists for a provider.

        Args:
            provider: Provider name

        Returns:
            True if API key exists, False otherwise
        """
        return keyring.get_password(cls.SERVICE_NAME, provider) is not None
