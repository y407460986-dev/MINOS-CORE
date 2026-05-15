"""OCR adapter boundary and optional OCR implementations."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Protocol


logger = logging.getLogger(__name__)

OCRBBox = tuple[float, float, float, float]


class OCRAdapterError(ValueError):
    """Raised when OCR input cannot be processed by the selected adapter."""


class OCRDependencyError(RuntimeError):
    """Raised when an optional OCR dependency is missing."""


@dataclass(frozen=True)
class OCRBlock:
    block_number: int
    text: str
    confidence: float | None = None
    bbox: OCRBBox | None = None
    engine: str = ""
    source_ref: str = ""


@dataclass(frozen=True)
class OCRPageText:
    page_number: int
    text: str
    confidence: float | None = None
    blocks: list[OCRBlock] = field(default_factory=list)
    bbox: OCRBBox | None = None
    engine: str = ""
    source_ref: str = ""


@dataclass(frozen=True)
class OCRResult:
    source_ref: str
    pages: list[OCRPageText] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages if page.text)


class OCRAdapter(Protocol):
    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        """Extract text from binary document content."""
        ...


class NotImplementedOCRAdapter:
    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        raise NotImplementedError("OCR adapter is not configured")


class FakeOCRAdapter:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        return OCRResult(
            source_ref=source_ref,
            pages=[OCRPageText(page_number=1, text=self.text, confidence=1.0)],
        )


class PyMuPDFTextLayerOCRAdapter:
    """Extract OCR-compatible text blocks from a PDF text layer."""

    engine = "pymupdf_text_layer"

    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        if not _looks_like_pdf(source_ref, content):
            raise OCRAdapterError(
                f"PyMuPDFTextLayerOCRAdapter only supports PDF input: {source_ref}"
            )

        fitz = _import_pymupdf("PyMuPDFTextLayerOCRAdapter")
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:  # pragma: no cover - depends on PyMuPDF internals
            raise OCRAdapterError(
                f"PDF text layer extraction failed for {source_ref}: {exc}"
            ) from exc

        try:
            pages: list[OCRPageText] = []
            for index, page in enumerate(document, start=1):
                page_text = _clean_page_text(page.get_text("text") or "")
                blocks = _pymupdf_blocks(page, source_ref, self.engine)
                if not page_text and blocks:
                    page_text = "\n".join(block.text for block in blocks if block.text)
                page_bbox = _page_bbox(page)
                pages.append(
                    OCRPageText(
                        page_number=index,
                        text=page_text,
                        confidence=1.0 if page_text or blocks else None,
                        blocks=blocks,
                        bbox=page_bbox,
                        engine=self.engine,
                        source_ref=source_ref,
                    )
                )
            return OCRResult(source_ref=source_ref, pages=pages)
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()


class RapidOCRPageAdapter:
    """Run RapidOCR on image files or rendered PDF pages."""

    engine = "rapidocr_onnxruntime"
    image_suffixes = {".png", ".jpg", ".jpeg"}

    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine

    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        ocr_engine = self._engine if self._engine is not None else _load_rapidocr_engine()
        if _looks_like_pdf(source_ref, content):
            return self._extract_pdf(source_ref, content, ocr_engine)
        if _looks_like_image(source_ref, content):
            return self._extract_image(source_ref, content, ocr_engine)
        raise OCRAdapterError(
            "RapidOCRPageAdapter supports only PNG, JPG, JPEG, or PDF input: "
            f"{source_ref}"
        )

    def _extract_image(self, source_ref: str, content: bytes, ocr_engine: Any) -> OCRResult:
        _require_pillow_for_image_validation("RapidOCRPageAdapter")
        image_input: Any = _image_path_or_bytes(source_ref, content)
        page = _rapidocr_page(
            ocr_engine=ocr_engine,
            image_input=image_input,
            source_ref=source_ref,
            page_number=1,
            page_bbox=_image_bbox(source_ref, content),
            engine_name=self.engine,
        )
        return OCRResult(source_ref=source_ref, pages=[page])

    def _extract_pdf(self, source_ref: str, content: bytes, ocr_engine: Any) -> OCRResult:
        fitz = _import_pymupdf("RapidOCRPageAdapter PDF OCR")
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:  # pragma: no cover - depends on PyMuPDF internals
            raise OCRAdapterError(f"PDF rendering for OCR failed for {source_ref}: {exc}") from exc

        try:
            pages: list[OCRPageText] = []
            for index, page in enumerate(document, start=1):
                try:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image_bytes = pixmap.tobytes("png")
                except Exception as exc:  # pragma: no cover - depends on PyMuPDF internals
                    raise OCRAdapterError(
                        f"PDF page rendering for OCR failed for {source_ref} page {index}: {exc}"
                    ) from exc
                pages.append(
                    _rapidocr_page(
                        ocr_engine=ocr_engine,
                        image_input=image_bytes,
                        source_ref=source_ref,
                        page_number=index,
                        page_bbox=_page_bbox(page),
                        engine_name=self.engine,
                    )
                )
            return OCRResult(source_ref=source_ref, pages=pages)
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()


class CompositeOCRAdapter:
    """Prefer PDF text-layer extraction and fall back to RapidOCR when needed."""

    def __init__(
        self,
        text_layer_adapter: OCRAdapter | None = None,
        page_adapter: OCRAdapter | None = None,
        min_text_length: int = 20,
    ) -> None:
        self.text_layer_adapter = text_layer_adapter or PyMuPDFTextLayerOCRAdapter()
        self.page_adapter = page_adapter or RapidOCRPageAdapter()
        self.min_text_length = min_text_length

    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        if _looks_like_pdf(source_ref, content):
            text_layer = self.text_layer_adapter.extract_text(source_ref, content)
            if len(_compact_text(text_layer.text)) >= self.min_text_length:
                return text_layer
        return self.page_adapter.extract_text(source_ref, content)


def _import_pymupdf(context: str) -> Any:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OCRDependencyError(
            f"{context} requires PyMuPDF (fitz); install minos-core[ocr]"
        ) from exc
    return fitz


def _load_rapidocr_engine() -> Any:
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OCRDependencyError(
            "RapidOCRPageAdapter requires rapidocr-onnxruntime; install minos-core[ocr]"
        ) from exc
    return RapidOCR()


def _require_pillow_for_image_validation(context: str) -> None:
    try:
        from PIL import Image  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:
        raise OCRDependencyError(
            f"{context} requires Pillow for image OCR; install minos-core[ocr]"
        ) from exc


def _looks_like_pdf(source_ref: str, content: bytes) -> bool:
    return Path(str(source_ref)).suffix.lower() == ".pdf" or content.startswith(b"%PDF")


def _looks_like_image(source_ref: str, content: bytes) -> bool:
    suffix = Path(str(source_ref)).suffix.lower()
    if suffix in RapidOCRPageAdapter.image_suffixes:
        return True
    return content.startswith(b"\x89PNG\r\n\x1a\n") or content.startswith(b"\xff\xd8")


def _image_path_or_bytes(source_ref: str, content: bytes) -> Any:
    path = Path(str(source_ref))
    if path.exists() and path.is_file():
        return str(path)
    return content


def _image_bbox(source_ref: str, content: bytes) -> OCRBBox | None:
    try:
        from PIL import Image

        path = Path(str(source_ref))
        if path.exists() and path.is_file():
            with Image.open(path) as image:
                width, height = image.size
        else:
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
    except Exception as exc:
        logger.debug("Image bbox extraction failed for %s: %s", source_ref, exc)
        return None
    return (0.0, 0.0, float(width), float(height))


def _rapidocr_page(
    *,
    ocr_engine: Any,
    image_input: Any,
    source_ref: str,
    page_number: int,
    page_bbox: OCRBBox | None,
    engine_name: str,
) -> OCRPageText:
    try:
        raw_result = ocr_engine(image_input)
    except Exception as exc:  # pragma: no cover - engine-specific
        raise OCRAdapterError(
            f"RapidOCR failed for {source_ref} page {page_number}: {exc}"
        ) from exc

    blocks = _rapidocr_blocks(raw_result, source_ref, page_number, engine_name)
    text = "\n".join(block.text for block in blocks if block.text)
    confidence_values = [block.confidence for block in blocks if block.confidence is not None]
    confidence = (
        sum(confidence_values) / len(confidence_values) if confidence_values else None
    )
    return OCRPageText(
        page_number=page_number,
        text=text,
        confidence=confidence,
        blocks=blocks,
        bbox=page_bbox,
        engine=engine_name,
        source_ref=source_ref,
    )


def _rapidocr_blocks(
    raw_result: Any,
    source_ref: str,
    page_number: int,
    engine_name: str,
) -> list[OCRBlock]:
    rows = _rapidocr_rows(raw_result)
    blocks: list[OCRBlock] = []
    for index, row in enumerate(rows, start=1):
        text, confidence, bbox = _rapidocr_row_values(row)
        if not text:
            continue
        blocks.append(
            OCRBlock(
                block_number=index,
                text=text,
                confidence=confidence,
                bbox=bbox,
                engine=engine_name,
                source_ref=f"{source_ref}#page={page_number}",
            )
        )
    return blocks


def _rapidocr_rows(raw_result: Any) -> list[Any]:
    if raw_result is None:
        return []
    if hasattr(raw_result, "boxes") and hasattr(raw_result, "txts"):
        boxes = list(getattr(raw_result, "boxes") or [])
        texts = list(getattr(raw_result, "txts") or [])
        scores = list(getattr(raw_result, "scores", []) or [])
        return [
            (box, text, scores[index] if index < len(scores) else None)
            for index, (box, text) in enumerate(zip(boxes, texts))
        ]
    if isinstance(raw_result, tuple) and raw_result:
        first = raw_result[0]
        if isinstance(first, list):
            return first
    if isinstance(raw_result, list):
        return raw_result
    return []


def _rapidocr_row_values(row: Any) -> tuple[str, float | None, OCRBBox | None]:
    if isinstance(row, dict):
        text = str(row.get("text", row.get("rec_text", ""))).strip()
        confidence = _float_or_none(row.get("confidence", row.get("score")))
        bbox = _bbox_from_any(row.get("bbox", row.get("box", row.get("points"))))
        return text, confidence, bbox
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        bbox = _bbox_from_any(row[0])
        text = str(row[1]).strip()
        confidence = _float_or_none(row[2]) if len(row) >= 3 else None
        return text, confidence, bbox
    return "", None, None


def _pymupdf_blocks(page: Any, source_ref: str, engine_name: str) -> list[OCRBlock]:
    blocks: list[OCRBlock] = []
    try:
        raw_blocks = page.get_text("blocks") or []
    except Exception as exc:
        logger.debug("PyMuPDF block extraction failed for %s: %s", source_ref, exc)
        return blocks
    for index, raw in enumerate(raw_blocks, start=1):
        if not isinstance(raw, (list, tuple)) or len(raw) < 5:
            continue
        text = _clean_page_text(str(raw[4]))
        if not text:
            continue
        blocks.append(
            OCRBlock(
                block_number=index,
                text=text,
                confidence=1.0,
                bbox=_bbox_from_any(raw[:4]),
                engine=engine_name,
                source_ref=source_ref,
            )
        )
    return blocks


def _page_bbox(page: Any) -> OCRBBox | None:
    rect = getattr(page, "rect", None)
    if rect is None:
        return None
    if all(hasattr(rect, attr) for attr in ("x0", "y0", "x1", "y1")):
        return (
            float(rect.x0),
            float(rect.y0),
            float(rect.x1),
            float(rect.y1),
        )
    return _bbox_from_any(rect)


def _bbox_from_any(value: Any) -> OCRBBox | None:
    if value is None:
        return None
    if isinstance(value, dict):
        left = _float_or_none(value.get("x", value.get("left")))
        top = _float_or_none(value.get("y", value.get("top")))
        right = _float_or_none(value.get("right"))
        bottom = _float_or_none(value.get("bottom"))
        width = _float_or_none(value.get("width", value.get("w")))
        height = _float_or_none(value.get("height", value.get("h")))
        if right is None and left is not None and width is not None:
            right = left + width
        if bottom is None and top is not None and height is not None:
            bottom = top + height
        if None not in (left, top, right, bottom):
            return (float(left), float(top), float(right), float(bottom))
    if isinstance(value, (list, tuple)):
        if len(value) >= 4 and all(_float_or_none(item) is not None for item in value[:4]):
            return (
                float(value[0]),
                float(value[1]),
                float(value[2]),
                float(value[3]),
            )
        points: list[tuple[float, float]] = []
        for point in value:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                x = _float_or_none(point[0])
                y = _float_or_none(point[1])
                if x is not None and y is not None:
                    points.append((x, y))
        if points:
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            return (min(xs), min(ys), max(xs), max(ys))
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value in {None, ""} else float(value)
    except (TypeError, ValueError):
        return None


def _clean_page_text(value: str) -> str:
    return "\n".join(line.strip() for line in str(value).splitlines() if line.strip())


def _compact_text(value: str) -> str:
    return "".join(str(value).split())
