"""Drawing file ingestion and page evidence creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .run_manifest import sha256_file


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
SUPPORTED_DRAWING_SUFFIXES = SUPPORTED_IMAGE_SUFFIXES | {".pdf"}


class DrawingInputError(ValueError):
    """Raised when a drawing source cannot be loaded or rendered."""


@dataclass(frozen=True)
class DrawingSource:
    source_id: str
    path: str
    file_name: str
    file_type: str
    sha256: str
    imported_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "path": self.path,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "sha256": self.sha256,
            "imported_at": self.imported_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DrawingPageEvidence:
    evidence_id: str
    source_id: str
    page_number: int
    image_path: str
    width: int
    height: int
    sha256: str
    source: str = "drawing_page"
    content: str = ""
    confidence: float = 1.0
    ai_inferred: bool = False
    needs_confirmation: bool = False

    def model_dump(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "source": self.source,
            "content": self.content,
            "page_number": self.page_number,
            "image_path": self.image_path,
            "width": self.width,
            "height": self.height,
            "sha256": self.sha256,
            "confidence": self.confidence,
            "ai_inferred": self.ai_inferred,
            "needs_confirmation": self.needs_confirmation,
        }


def load_drawing_source(path: str | Path) -> DrawingSource:
    """Validate a drawing path and create a stable source record."""

    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"drawing source not found: {source_path}")
    if not source_path.is_file():
        raise DrawingInputError(f"drawing source must be a file: {source_path}")
    suffix = source_path.suffix.lower()
    if suffix not in SUPPORTED_DRAWING_SUFFIXES:
        raise DrawingInputError(f"unsupported drawing file type: {suffix}")

    digest = sha256_file(source_path)
    return DrawingSource(
        source_id=f"drawing_{digest[:12]}",
        path=str(source_path),
        file_name=source_path.name,
        file_type=suffix.lstrip("."),
        sha256=digest,
        imported_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


def render_drawing_pages(
    source: DrawingSource | str | Path,
    output_dir: str | Path | None = None,
) -> list[DrawingPageEvidence]:
    """Render or normalize drawing pages into image-backed evidence records.

    PNG/JPG inputs are copied into evidence records without rewriting the file.
    PDF rendering uses PyMuPDF when available; if it is not installed, the
    function fails explicitly instead of returning fake page evidence.
    """

    drawing_source = load_drawing_source(source) if not isinstance(source, DrawingSource) else source
    source_path = Path(drawing_source.path)
    suffix = source_path.suffix.lower()
    if suffix in SUPPORTED_IMAGE_SUFFIXES:
        return [_image_page_evidence(drawing_source, source_path, 1)]
    if suffix == ".pdf":
        return _render_pdf_pages(drawing_source, output_dir)
    raise DrawingInputError(f"unsupported drawing file type: {suffix}")


def drawing_pages_to_evidence_bundle(
    source: DrawingSource,
    pages: list[DrawingPageEvidence],
) -> dict[str, Any]:
    """Return a MINOS evidence bundle for drawing page evidence."""

    return {
        "document_type": "evidence_bundle",
        "schema_version": "minos-core.drawing_evidence.v1",
        "source": source.model_dump(),
        "evidence": [page.model_dump() for page in pages],
    }


def _image_page_evidence(
    source: DrawingSource,
    image_path: Path,
    page_number: int,
) -> DrawingPageEvidence:
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
    except Exception as exc:  # noqa: BLE001 - preserve original image failure context
        raise DrawingInputError(f"drawing image cannot be opened: {image_path}: {exc}") from exc

    digest = sha256_file(image_path)
    return DrawingPageEvidence(
        evidence_id=f"drawing_page_{page_number:03d}",
        source_id=source.source_id,
        page_number=page_number,
        image_path=str(image_path),
        width=width,
        height=height,
        sha256=digest,
        content=f"{source.file_name} page {page_number}",
    )


def _render_pdf_pages(
    source: DrawingSource,
    output_dir: str | Path | None,
) -> list[DrawingPageEvidence]:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DrawingInputError(
            "PDF rendering requires PyMuPDF (fitz); install the PDF renderer before importing PDF drawings"
        ) from exc

    target_dir = Path(output_dir) if output_dir is not None else Path(source.path).with_suffix("")
    target_dir.mkdir(parents=True, exist_ok=True)
    pages: list[DrawingPageEvidence] = []
    try:
        document = fitz.open(source.path)
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image_path = target_dir / f"{Path(source.file_name).stem}_page_{index:03d}.png"
            pixmap.save(str(image_path))
            pages.append(_image_page_evidence(source, image_path, index))
    except Exception as exc:  # noqa: BLE001 - keep renderer errors explicit
        raise DrawingInputError(f"PDF rendering failed for {source.path}: {exc}") from exc
    if not pages:
        raise DrawingInputError(f"PDF rendering produced no pages: {source.path}")
    return pages
