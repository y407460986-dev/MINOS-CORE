"""Manage persistent authentication tokens using system keyring."""

import secrets

from .api_key_store import SecureAPIKeyStore


class TokenManager:
    """Manage persistent authentication tokens using system keyring."""

    TOKEN_PROVIDER = "minos-desktop-api-token"

    def __init__(self) -> None:
        self.keystore = SecureAPIKeyStore()

    def get_or_create_token(self) -> str:
        """
        Get existing token or generate new one.

        Returns:
            Persistent authentication token

        Raises:
            RuntimeError: If keyring is unavailable
        """
        try:
            secret_token = self.keystore.get_api_key(self.TOKEN_PROVIDER)
            if secret_token is None:
                token = secrets.token_urlsafe(32)
                self.keystore.store_api_key(self.TOKEN_PROVIDER, token)
                return token
            return secret_token.get_secret_value()
        except Exception as e:
            raise RuntimeError(
                f"Failed to access system keyring: {e}. "
                "Ensure keyring backend is available and unlocked."
            ) from e

    def regenerate_token(self) -> str:
        """
        Generate new token and store it.

        Returns:
            New authentication token

        Raises:
            RuntimeError: If keyring is unavailable
        """
        try:
            token = secrets.token_urlsafe(32)
            self.keystore.store_api_key(self.TOKEN_PROVIDER, token)
            return token
        except Exception as e:
            raise RuntimeError(
                f"Failed to store token in keyring: {e}. "
                "Ensure keyring backend is available and unlocked."
            ) from e
