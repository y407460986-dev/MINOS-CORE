"""Settings management for desktop application."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from minos_core.ai_config import load_openai_responses_config

from ..app_state import DesktopAIConfigState
from ..security.api_key_store import SecureAPIKeyStore
from ..security.secret_str import SecretStr
from .sqlite_store import DesktopSQLiteStore, DEFAULT_DESKTOP_DB_PATH, _utc_now

from minos_core._paths import user_data_dir

DEFAULT_DESKTOP_OUTPUT_DIR = user_data_dir() / "out"


class DesktopSettingsStore:
    """Manages application settings stored in SQLite database."""

    def __init__(self, db_path: str | Path = DEFAULT_DESKTOP_DB_PATH) -> None:
        self._store = DesktopSQLiteStore(db_path)

    def get_default_output_dir(self) -> str:
        """Get the default output directory."""
        value = self._get("default_output_dir")
        if value:
            return value
        return str(DEFAULT_DESKTOP_OUTPUT_DIR)

    def set_default_output_dir(self, output_dir: str | Path) -> str:
        """Set the default output directory."""
        value = str(Path(output_dir))
        self._set("default_output_dir", value)
        return value

    def get_ai_overrides(self) -> dict[str, str | None]:
        """Get AI configuration overrides. API key from keyring, others from SQLite."""
        keystore = SecureAPIKeyStore()
        api_key = None
        if self._get("ai_api_key_configured") == "true":
            secret_key = keystore.get_api_key("openai")
            if secret_key is not None:
                api_key = secret_key.get_secret_value()

        return {
            "base_url": self._get("ai_base_url") or None,
            "api_key": api_key,
            "model": self._get("ai_model") or None,
        }

    def set_ai_overrides(
        self,
        *,
        base_url: str | None = None,
        api_key: str | SecretStr | None = None,
        model: str | None = None,
    ) -> dict[str, str | None]:
        """Set AI configuration overrides. API keys go to keyring, others to SQLite."""
        if base_url is not None:
            self._set("ai_base_url", _normalize_ai_base_url(base_url))
        if api_key is not None:
            # Extract secret value if SecretStr
            key_value = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
            # Store in keyring instead of SQLite
            keystore = SecureAPIKeyStore()
            keystore.store_api_key("openai", key_value.strip())
            # Store flag in SQLite (not the key itself)
            self._set("ai_api_key_configured", "true")
        if model is not None:
            self._set("ai_model", model.strip())
        return self.get_ai_overrides()

    def get_ai_config_state(self) -> DesktopAIConfigState:
        """Get complete AI configuration state including environment variables."""
        ai_overrides = self.get_ai_overrides()
        config = load_openai_responses_config(db_overrides=ai_overrides)
        model_env = _first_env_name(("MINOS_OPENAI_MODEL", "OPENAI_MODEL", "ARK_MODEL"))
        base_url_env = _first_env_name(
            ("MINOS_OPENAI_BASE_URL", "OPENAI_BASE_URL", "ARK_BASE_URL")
        )
        api_key_env = _first_env_name(("MINOS_OPENAI_API_KEY", "OPENAI_API_KEY"))
        return DesktopAIConfigState(
            provider=config.provider,
            model=config.model,
            model_configured=bool(config.model),
            model_source=model_env or ("user_settings" if ai_overrides["model"] else "default"),
            base_url=config.base_url,
            base_url_configured=bool(config.base_url),
            base_url_source=base_url_env or ("user_settings" if ai_overrides["base_url"] else "default"),
            api_key_configured=config.api_key_configured,
            api_key_source=config.api_key_source,
            api_key_env_name=config.api_key_env_name,
            wire_api=config.wire_api,
            responses_path=config.responses_path,
            base_url_override=ai_overrides["base_url"],
            api_key_override_set=bool(ai_overrides["api_key"]),
            model_override=ai_overrides["model"],
            base_url_locked_by_env=bool(base_url_env),
            api_key_locked_by_env=bool(api_key_env),
            model_locked_by_env=bool(model_env),
        )

    def _get(self, key: str) -> str:
        """Get a setting value by key."""
        with self._store.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return str(row["value"]) if row else ""

    def _set(self, key: str, value: str) -> None:
        """Set a setting value by key."""
        now = _utc_now()
        with self._store.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )


def _first_env_name(names: tuple[str, ...]) -> str:
    """Return the first environment variable name that is set."""
    for name in names:
        if os.getenv(name):
            return name
    return ""


def _normalize_ai_base_url(value: str) -> str:
    """Normalize and validate AI base URL."""
    normalized = value.strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme == "https":
        return normalized
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return normalized
    raise ValueError("AI 服务地址必须使用 HTTPS；本机 127.0.0.1/localhost 代理可使用 HTTP。")
