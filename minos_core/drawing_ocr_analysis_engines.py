"""OCR engine adapter dispatch for drawing OCR analysis."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters.ocr import (
    PyMuPDFTextLayerOCRAdapter,
    RapidOCRPageAdapter,
)


def _ocr_adapter_for_engine(ocr_engine: str) -> Any:
    engine = str(ocr_engine or "auto").strip().lower()
    if engine == "auto":
        from .adapters.mineru_ocr import MinerUOCRAdapter

        return MinerUOCRAdapter()
    if engine == "pdf_text":
        return PyMuPDFTextLayerOCRAdapter()
    if engine == "rapidocr":
        return RapidOCRPageAdapter()
    if engine == "mineru":
        from .adapters.mineru_ocr import MinerUOCRAdapter

        return MinerUOCRAdapter()
    raise ValueError("ocr_engine must be one of: auto, pdf_text, rapidocr, mineru")


def _source_path(source: Any) -> Path | None:
    path_value = getattr(source, "path", None)
    if path_value is None and isinstance(source, dict):
        path_value = source.get("path")
    if path_value is None:
        return None
    path = Path(str(path_value))
    return path if path.exists() and path.is_file() else None


def _source_ref(source: Any) -> str:
    for attr in ("path", "source_ref", "file_name", "source_id"):
        value = getattr(source, attr, None)
        if value:
            return str(value)
    if isinstance(source, dict):
        for key in ("path", "source_ref", "file_name", "source_id"):
            value = source.get(key)
            if value:
                return str(value)
    return "drawing"


_OCR_CORRECTIONS: dict[str, str] = {
    "较链": "铰链",
    "银件": "锻件",
    "朝质模管件": "钢质模锻件",
    "模管件": "模锻件",
    "性偿要求": "性能要求",
    "可遍测性": "可追溯性",
    "气氢腐性": "气氛腐蚀",
    "盐雾试册": "盐雾试验",
    "模被件": "模锻件",
}


def _correct_ocr_text(text: str) -> str:
    for wrong, right in _OCR_CORRECTIONS.items():
        text = text.replace(wrong, right)
    return text


def _source_bytes(source_path: Path | None) -> bytes:
    if source_path is None:
        raise ValueError("OCR drawing analysis requires a readable drawing source path")
    return source_path.read_bytes()
