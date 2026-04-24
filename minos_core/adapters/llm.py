"""LLM adapter boundary placeholders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str = "fake"
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMAdapter(Protocol):
    def complete(self, messages: list[LLMMessage]) -> LLMResult:
        """Generate a completion from structured messages."""
        ...


class NotImplementedLLMAdapter:
    def complete(self, messages: list[LLMMessage]) -> LLMResult:
        raise NotImplementedError("LLM adapter is not configured")


class FakeLLMAdapter:
    def __init__(self, content: str = "") -> None:
        self.content = content

    def complete(self, messages: list[LLMMessage]) -> LLMResult:
        return LLMResult(
            content=self.content,
            model="fake",
            metadata={"message_count": len(messages)},
        )
