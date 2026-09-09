"""Visual evidence crop helpers for drawing special characteristic review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image


def build_visual_evidence_regions(
    *,
    page_image_path: str | Path,
    page_evidence_id: str,
    technical_requirements: list[dict[str, Any]],
    output_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    source_path = Path(page_image_path)
    target_dir = Path(output_dir) if output_dir else source_path.parent / "visual_evidence"
    target_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        source = image.convert("RGB")

    width, height = source.size
    specs: list[tuple[str, tuple[float, float, float, float], list[str]]] = [
        ("full_page", (0.0, 0.0, 1.0, 1.0), [page_evidence_id]),
        ("title_block_special_counts", (0.72, 0.72, 1.0, 1.0), [page_evidence_id]),
        ("key_product_characteristic_table", (0.35, 0.0, 0.66, 0.12), [page_evidence_id]),
        ("technical_requirements", (0.56, 0.45, 1.0, 0.72), [page_evidence_id]),
    ]
    for line_index in range(1, 13):
        top = 0.45 + (line_index - 1) * 0.023
        bottom = min(0.72, top + 0.04)
        specs.append(
            (
                f"technical_requirement_line_{line_index:03d}",
                (0.56, top, 1.0, bottom),
                [page_evidence_id],
            )
        )

    for index, item in enumerate(technical_requirements, start=1):
        top = min(0.72, 0.45 + (index - 1) * 0.028)
        bottom = min(0.78, top + 0.05)
        evidence_refs = _evidence_refs(item, page_evidence_id)
        specs.append((f"technical_requirement_{index:03d}", (0.56, top, 1.0, bottom), evidence_refs))

    regions: list[dict[str, Any]] = []
    for label, ratio_box, evidence_refs in specs:
        box = _crop_box(width, height, ratio_box)
        image_path = target_dir / f"{page_evidence_id}_{label}.png"
        source.crop(box).save(image_path)
        regions.append(
            {
                "region_id": f"{page_evidence_id}_{label}",
                "page_evidence_id": page_evidence_id,
                "label": label,
                "bbox": list(box),
                "image_path": str(image_path),
                "evidence_refs": evidence_refs,
            }
        )
    return regions


def _crop_box(width: int, height: int, region: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    left, top, right, bottom = region
    x1 = max(0, min(width - 1, round(width * left)))
    y1 = max(0, min(height - 1, round(height * top)))
    x2 = max(x1 + 1, min(width, round(width * right)))
    y2 = max(y1 + 1, min(height, round(height * bottom)))
    return (x1, y1, x2, y2)


def _evidence_refs(item: dict[str, Any], fallback: str) -> list[str]:
    refs = item.get("evidence_refs")
    if not isinstance(refs, list):
        return [fallback]
    values = [str(ref) for ref in refs if str(ref)]
    return values or [fallback]
