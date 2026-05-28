"""Configuration provenance helpers used by ``minos-core doctor``.

Operators frequently need to know *where* a config value came from when
diagnosing surprising behaviour. This module inspects the limited set of
sources MINOS-CORE consults for AI configuration today and returns a list of
:class:`ConfigSource` records describing the resolution outcome. The
representation is intentionally lightweight; if more layers join later they
can be appended here without changing the public surface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ConfigSource",
    "describe_config_sources",
    "format_config_sources",
]


@dataclass(frozen=True)
class ConfigSource:
    """Where a configuration value resolved from."""

    key: str
    value: str
    source: str  # "env" | "file" | "default" | "unset"
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "detail": self.detail,
        }


def _redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}…{value[-3:]} (len={len(value)})"


def _env_source(
    key: str,
    env_names: tuple[str, ...],
    *,
    secret: bool = False,
    default: str | None = None,
) -> ConfigSource:
    """Resolve a value from the first matching env var, else ``default``."""

    for name in env_names:
        raw = os.getenv(name)
        if raw:
            display = _redact_secret(raw) if secret else raw
            return ConfigSource(key=key, value=display, source="env", detail=name)
    if default is not None:
        return ConfigSource(
            key=key,
            value=default,
            source="default",
            detail=f"hardcoded default; checked {', '.join(env_names)}",
        )
    return ConfigSource(
        key=key,
        value="",
        source="unset",
        detail=f"none of {', '.join(env_names)} are set",
    )


def _codex_config_source(key: str) -> ConfigSource:
    """Report whether the optional Codex config file is present."""

    home_env = os.getenv("MINOS_CODEX_HOME") or os.getenv("CODEX_HOME")
    base = Path(home_env) if home_env else None
    if base is None:
        user_profile = os.getenv("USERPROFILE") or os.getenv("HOME")
        if user_profile:
            base = Path(user_profile) / ".codex"
    if base is None:
        return ConfigSource(
            key=key, value="", source="unset", detail="no HOME/USERPROFILE set"
        )
    config_path = base / "config.toml"
    if config_path.exists():
        return ConfigSource(
            key=key,
            value=str(config_path),
            source="file",
            detail="codex config",
        )
    return ConfigSource(
        key=key,
        value=str(config_path),
        source="unset",
        detail="codex config file not present",
    )


def describe_config_sources() -> list[ConfigSource]:
    """Inspect the live process environment and return resolved sources."""

    sources: list[ConfigSource] = []

    sources.append(
        _env_source(
            "log_level",
            ("MINOS_LOG_LEVEL",),
            default="INFO",
        )
    )
    sources.append(
        _env_source(
            "log_json",
            ("MINOS_LOG_JSON",),
            default="false",
        )
    )
    sources.append(
        _env_source(
            "ai_base_url",
            (
                "MINOS_OPENAI_BASE_URL",
                "OPENAI_BASE_URL",
                "ARK_BASE_URL",
            ),
            default="https://cx.allincoding.cc",
        )
    )
    sources.append(
        _env_source(
            "ai_model",
            ("MINOS_OPENAI_MODEL", "OPENAI_MODEL", "ARK_MODEL"),
            default="gpt-5.5",
        )
    )
    sources.append(
        _env_source(
            "ai_api_key",
            ("MINOS_OPENAI_API_KEY", "OPENAI_API_KEY", "ARK_API_KEY"),
            secret=True,
        )
    )
    sources.append(
        _env_source(
            "backup_ai_endpoints",
            ("MINOS_BACKUP_AI_ENDPOINTS",),
        )
    )
    sources.append(
        _env_source(
            "mineru_command",
            ("MINOS_MINERU_COMMAND", "MINERU_COMMAND"),
        )
    )
    sources.append(_codex_config_source("codex_config_file"))

    return sources


def format_config_sources(sources: list[ConfigSource]) -> str:
    """Render the source list for human consumption (``doctor`` output)."""

    if not sources:
        return "(no configuration sources detected)"
    width_key = max(len(s.key) for s in sources)
    width_source = max(len(s.source) for s in sources)
    lines: list[str] = []
    for src in sources:
        value = src.value or "(empty)"
        detail = f"  [{src.detail}]" if src.detail else ""
        lines.append(
            f"  {src.key.ljust(width_key)}  {src.source.ljust(width_source)}  {value}{detail}"
        )
    return "\n".join(lines)
