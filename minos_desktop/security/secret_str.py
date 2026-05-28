"""Secure string type that prevents accidental exposure of secrets."""

from typing import Any

try:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import core_schema
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


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

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: "GetCoreSchemaHandler"
    ) -> "core_schema.CoreSchema":
        """Pydantic v2 schema generation."""
        if not HAS_PYDANTIC:
            raise ImportError("Pydantic is required for schema generation")

        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: instance.get_secret_value(),
                return_schema=core_schema.str_schema(),
            ),
        )

    @classmethod
    def _validate(cls, value: Any) -> "SecretStr":
        """Validate and convert input to SecretStr."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(value)
        raise TypeError(f"SecretStr requires str, got {type(value).__name__}")
