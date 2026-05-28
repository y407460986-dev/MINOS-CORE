"""Secure string type that prevents accidental exposure of secrets."""

from typing import Any


class SecretStr:
    """
    A string wrapper that prevents accidental exposure of sensitive data.

    The secret value is never exposed in repr(), str(), or logs.
    """

    def __init__(self, secret: str):
        """
        Initialize SecretStr.

        Args:
            secret: The secret string to protect
        """
        if not isinstance(secret, str):
            raise TypeError(f"SecretStr requires str, got {type(secret).__name__}")

        self._secret = secret

    def get_secret_value(self) -> str:
        """
        Get the actual secret value.

        Returns:
            The secret string
        """
        return self._secret

    def __repr__(self) -> str:
        """Return safe representation."""
        return "SecretStr('**********')"

    def __str__(self) -> str:
        """Return safe string representation."""
        return "**********"

    def __eq__(self, other: Any) -> bool:
        """Compare with another SecretStr."""
        if isinstance(other, SecretStr):
            return self._secret == other._secret
        return False

    def __hash__(self) -> int:
        """Return hash of the secret."""
        return hash(self._secret)

    def __len__(self) -> int:
        """Return length of the secret."""
        return len(self._secret)

    def __bool__(self) -> bool:
        """Return True if secret is non-empty."""
        return bool(self._secret)
