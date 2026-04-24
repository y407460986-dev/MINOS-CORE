"""OCR adapter boundary placeholders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OCRPageText:
    page_number: int
    text: str
    confidence: float | None = None


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
