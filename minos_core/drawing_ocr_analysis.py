"""Build drawing analysis bundles from OCR text evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .drawing_ocr_analysis_core import (
    build_drawing_analysis_bundle_from_ocr,
)
from .drawing_ocr_analysis_engines import (
    _ocr_adapter_for_engine,
    _source_bytes,
    _source_path,
    _source_ref,
)


def analyze_drawing_with_ocr(
    *,
    source: Any,
    pages: list[Any],
    output_dir: str | Path,
    context: dict[str, Any] | None = None,
    ocr_engine: str = "auto",
    ocr_adapter: Any | None = None,
) -> dict[str, Any]:
    """Run OCR over the drawing source and return a drawing_analysis bundle.

    /// 1. Pick the configured OCR adapter: MinerU-first by default, with explicit PDF text and RapidOCR fallbacks.
    /// 2. Extract OCR page/block evidence from the original drawing bytes.
    /// 3. Convert OCR evidence into the same drawing_analysis contract used downstream.
    """

    del output_dir
    source_path = _source_path(source)
    source_ref = str(source_path or _source_ref(source))
    content = _source_bytes(source_path)
    adapter = ocr_adapter or _ocr_adapter_for_engine(ocr_engine)
    result = adapter.extract_text(source_ref, content)
    return build_drawing_analysis_bundle_from_ocr(pages, result, context)
