"""AI provider configuration helpers for MINOS."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]


DEFAULT_OPENAI_RESPONSES_BASE_URL = "https://cx.allincoding.cc"
_DB_OVERRIDES_PROVIDER: Callable[[], dict[str, Any] | None] | None = None


@dataclass(frozen=True)
class AIProviderConfig:
    provider: str
    model: str
    base_url: str
    api_key_configured: bool
    api_key_env_name: str
    api_key_source: str = ""
    codex_config_path: str = ""
    codex_auth_path: str = ""
    wire_api: str = "responses"
    responses_path: str = "responses"
    requires_openai_auth: bool = False
    store: bool | None = None
    reasoning_effort: str = ""
    user_agent: str = "minos-core"

    def model_dump(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_configured": self.api_key_configured,
            "api_key_env_name": self.api_key_env_name,
            "api_key_source": self.api_key_source,
            "codex_config_path": self.codex_config_path,
            "codex_auth_path": self.codex_auth_path,
            "wire_api": self.wire_api,
            "responses_path": self.responses_path,
            "requires_openai_auth": self.requires_openai_auth,
            "store": self.store,
            "reasoning_effort": self.reasoning_effort,
            "user_agent": self.user_agent,
        }


@dataclass(frozen=True)
class _ResolvedAPIKey:
    value: str
    source: str
    env_name: str = ""
    auth_path: str = ""


def load_openai_responses_config(
    *,
    codex_home: str | Path | None = None,
    allow_codex_config: bool | None = None,
    db_overrides: dict[str, Any] | None = None,
) -> AIProviderConfig:
    """Load OpenAI-compatible Responses API config without exposing secrets."""

    db_overrides = _normalize_db_overrides(db_overrides)
    allow_codex = _allow_codex_config(allow_codex_config)
    codex_config = _load_codex_config(codex_home) if allow_codex else {}
    key = resolve_openai_api_key(
        codex_home=codex_home,
        allow_codex_config=allow_codex,
        prefer_codex_auth=_codex_requires_openai_auth(codex_config),
        db_overrides=db_overrides,
    )
    model = (
        os.getenv("MINOS_OPENAI_MODEL")
        or os.getenv("OPENAI_MODEL")
        or os.getenv("ARK_MODEL")
        or db_overrides.get("model")
        or "gpt-5.5"
    )
    env_base_url_name = _first_set_env_name(
        ("MINOS_OPENAI_BASE_URL", "OPENAI_BASE_URL", "ARK_BASE_URL")
    )
    codex_base_url = _codex_base_url(codex_config)
    # Fix empty string check logic
    env_base_url = os.getenv(env_base_url_name, "") if env_base_url_name else ""
    base_url = env_base_url or db_overrides.get("base_url") or DEFAULT_OPENAI_RESPONSES_BASE_URL
    codex_config_path = _codex_file(codex_home, "config.toml") if allow_codex else None
    return AIProviderConfig(
        provider="openai_responses",
        model=model,
        base_url=base_url.rstrip("/"),
        api_key_configured=bool(key.value),
        api_key_env_name=key.env_name,
        api_key_source=key.source,
        codex_config_path=(
            str(codex_config_path) if codex_config_path and codex_config_path.exists() else ""
        ),
        codex_auth_path=key.auth_path,
        wire_api=_codex_wire_api(codex_config) or "responses",
        responses_path=_responses_path(base_url, not env_base_url_name and bool(codex_base_url)),
        requires_openai_auth=_codex_requires_openai_auth(codex_config),
        store=_store_from_codex(codex_config),
        reasoning_effort=_reasoning_effort(codex_config),
        user_agent=_user_agent(codex_config),
    )


def load_openai_api_key(
    *,
    codex_home: str | Path | None = None,
    allow_codex_config: bool | None = None,
    db_overrides: dict[str, Any] | None = None,
) -> str:
    """Return the configured API key for runtime use; callers must never log it."""

    return resolve_openai_api_key(
        codex_home=codex_home,
        allow_codex_config=_allow_codex_config(allow_codex_config),
        prefer_codex_auth=_codex_requires_openai_auth(
            _load_codex_config(codex_home) if _allow_codex_config(allow_codex_config) else {}
        ),
        db_overrides=db_overrides,
    ).value


def resolve_openai_api_key(
    *,
    codex_home: str | Path | None = None,
    allow_codex_config: bool = True,
    prefer_codex_auth: bool = False,
    db_overrides: dict[str, Any] | None = None,
) -> _ResolvedAPIKey:
    db_overrides = _normalize_db_overrides(db_overrides)
    key_name = _first_set_env_name(("MINOS_OPENAI_API_KEY", "OPENAI_API_KEY"))
    if key_name:
        return _ResolvedAPIKey(
            value=os.getenv(key_name, ""),
            source="environment",
            env_name=key_name,
        )

    db_key = db_overrides.get("api_key", "")
    if db_key:
        return _ResolvedAPIKey(value=db_key, source="user_settings")

    if allow_codex_config and prefer_codex_auth:
        key = _codex_auth_key(codex_home)
        if key.value:
            return key

    ark_key_name = _first_set_env_name(("ARK_API_KEY",))
    if ark_key_name:
        return _ResolvedAPIKey(
            value=os.getenv(ark_key_name, ""),
            source="environment",
            env_name=ark_key_name,
        )

    if not allow_codex_config:
        return _ResolvedAPIKey(value="", source="")

    key = _codex_auth_key(codex_home)
    if key.value:
        return key
    return _ResolvedAPIKey(value="", source="")


def register_db_overrides_provider(
    provider: Callable[[], dict[str, Any] | None] | None,
) -> None:
    global _DB_OVERRIDES_PROVIDER
    _DB_OVERRIDES_PROVIDER = provider


def _normalize_db_overrides(overrides: dict[str, Any] | None) -> dict[str, str]:
    raw = overrides if overrides is not None else _read_db_overrides()
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, str] = {}
    for key in ("base_url", "api_key", "model"):
        value = raw.get(key)
        if isinstance(value, str):
            normalized[key] = value.strip()
    return normalized


def _read_db_overrides() -> dict[str, Any]:
    if _DB_OVERRIDES_PROVIDER is None:
        return {}
    try:
        return _DB_OVERRIDES_PROVIDER() or {}
    except Exception:
        return {}


def _codex_auth_key(codex_home: str | Path | None = None) -> _ResolvedAPIKey:
    auth_path = _codex_file(codex_home, "auth.json")
    auth = _load_json_object(auth_path)
    key = auth.get("OPENAI_API_KEY")
    if isinstance(key, str) and key:
        return _ResolvedAPIKey(
            value=key,
            source="codex_auth",
            auth_path=str(auth_path),
        )
    return _ResolvedAPIKey(value="", source="")


def _first_set_env_name(names: tuple[str, ...]) -> str:
    for name in names:
        if os.getenv(name):
            return name
    return ""


def _allow_codex_config(override: bool | None) -> bool:
    if override is not None:
        return override
    return os.getenv("MINOS_DISABLE_CODEX_CONFIG", "").lower() not in {"1", "true", "yes"}


def _codex_home(codex_home: str | Path | None = None) -> Path:
    if codex_home:
        return Path(codex_home)
    env_home = os.getenv("MINOS_CODEX_HOME") or os.getenv("CODEX_HOME")
    if env_home:
        return Path(env_home)
    user_profile = os.getenv("USERPROFILE")
    if user_profile:
        return Path(user_profile) / ".codex"
    home = os.getenv("HOME")
    if home:
        return Path(home) / ".codex"
    try:
        return Path.home() / ".codex"
    except RuntimeError:
        return Path("__missing_home__") / ".codex"


def _codex_file(codex_home: str | Path | None, filename: str) -> Path:
    return _codex_home(codex_home) / filename


def _load_codex_config(codex_home: str | Path | None = None) -> dict[str, Any]:
    path = _codex_file(codex_home, "config.toml")
    if not path.exists():
        return {}
    if tomllib is not None:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return data if isinstance(data, dict) else {}
    return _parse_minimal_toml(path.read_text(encoding="utf-8"))


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _codex_base_url(config: dict[str, Any]) -> str:
    provider_name = config.get("model_provider")
    providers = config.get("model_providers")
    if not isinstance(provider_name, str) or not isinstance(providers, dict):
        return ""
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        return ""
    base_url = provider.get("base_url")
    return base_url if isinstance(base_url, str) else ""


def _codex_wire_api(config: dict[str, Any]) -> str:
    provider_name = config.get("model_provider")
    providers = config.get("model_providers")
    if not isinstance(provider_name, str) or not isinstance(providers, dict):
        return ""
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        return ""
    wire_api = provider.get("wire_api")
    return wire_api if isinstance(wire_api, str) else ""


def _codex_requires_openai_auth(config: dict[str, Any]) -> bool:
    provider_name = config.get("model_provider")
    providers = config.get("model_providers")
    if not isinstance(provider_name, str) or not isinstance(providers, dict):
        return False
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        return False
    return provider.get("requires_openai_auth") is True


def _store_from_codex(config: dict[str, Any]) -> bool | None:
    if config.get("disable_response_storage") is True:
        return False
    return None


def _reasoning_effort(config: dict[str, Any]) -> str:
    value = (
        os.getenv("MINOS_OPENAI_REASONING_EFFORT")
        or os.getenv("OPENAI_REASONING_EFFORT")
        or os.getenv("ARK_REASONING_EFFORT")
        or config.get("model_reasoning_effort")
    )
    return value if isinstance(value, str) else ""


def _user_agent(config: dict[str, Any]) -> str:
    if config:
        return "codex-cli"
    return "minos-core"


def _responses_path(base_url: str, has_codex_base_url: bool) -> str:
    normalized = base_url.rstrip("/")
    if normalized == DEFAULT_OPENAI_RESPONSES_BASE_URL:
        return "responses"
    if normalized.endswith("/v1"):
        return "responses"
    if has_codex_base_url:
        return "responses"
    return "v1/responses"


def _parse_minimal_toml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current = root
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = root
            for part in line[1:-1].split("."):
                current = current.setdefault(part, {})
            continue
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        current[key] = _parse_minimal_toml_value(value)
    return root


def _parse_minimal_toml_value(value: str) -> Any:
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value
