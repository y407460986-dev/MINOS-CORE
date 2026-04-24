"""Sample configuration loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SAMPLES_DIR = Path(__file__).resolve().parent.parent / "configs" / "samples"


@dataclass(frozen=True)
class SampleMetadata:
    sample_id: str
    display_name: str
    product_family: str
    apqp_phase: str
    language: str
    workbook_name: str
    default_export_format: str
    path: Path

    @classmethod
    def from_mapping(cls, data: dict[str, Any], path: Path) -> "SampleMetadata":
        deliverable = data.get("deliverable", {})
        return cls(
            sample_id=str(data.get("sample_id", "")),
            display_name=str(data.get("display_name", "")),
            product_family=str(data.get("product_family", "")),
            apqp_phase=str(data.get("apqp_phase", "")),
            language=str(data.get("language", "")),
            workbook_name=str(deliverable.get("workbook_name", "")),
            default_export_format=str(deliverable.get("default_export_format", "")),
            path=path,
        )


def list_samples(samples_dir: str | Path | None = None) -> list[SampleMetadata]:
    root = Path(samples_dir) if samples_dir is not None else SAMPLES_DIR
    if not root.exists():
        return []
    samples = [load_sample_metadata(path) for path in sorted(root.glob("*.json"))]
    return sorted(samples, key=lambda item: item.sample_id)


def load_sample_metadata(path: str | Path) -> SampleMetadata:
    sample_path = Path(path)
    with sample_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"sample metadata must be a JSON object: {sample_path}")
    return SampleMetadata.from_mapping(data, sample_path)
