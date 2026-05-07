"""Stage context and result envelope types."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from ..domain import APQPChain
from ..quality_gates import StageQualityGate


@dataclass(frozen=True)
class StageContext:
    stage: str
    fixture: str | Path | dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    chain: APQPChain | None = None
    output_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "fixture": str(self.fixture) if self.fixture is not None else None,
            "has_payload": self.payload is not None,
            "has_chain": self.chain is not None,
            "output_path": str(self.output_path)
            if self.output_path is not None
            else None,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str
    output: Any = None
    evidence: list[Any] = field(default_factory=list)
    pending_fields: list[str] = field(default_factory=list)
    ai_inferred_items: list[str] = field(default_factory=list)
    quality_gate: StageQualityGate | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def model_dump(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "output": _dump_value(self.output),
            "evidence": [_dump_value(item) for item in self.evidence],
            "pending_fields": self.pending_fields,
            "ai_inferred_items": self.ai_inferred_items,
            "quality_gate": self.quality_gate.model_dump()
            if self.quality_gate
            else None,
        }


def _dump_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return vars(value)
    return value
