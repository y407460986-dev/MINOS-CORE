"""
OCR engine detection and automatic selection.

Automatically detects available OCR engines and selects the best one
based on availability and capabilities.
"""

import os
import shutil
import logging
from typing import Literal

logger = logging.getLogger(__name__)

OCREngine = Literal["mineru", "rapidocr", "pdf_text"]


def detect_available_ocr_engines() -> list[OCREngine]:
    """
    Detect which OCR engines are available in the current environment.

    Returns:
        List of available OCR engine names, in order of preference
    """
    engines: list[OCREngine] = []

    # Check for RapidOCR
    try:
        import rapidocr_onnxruntime

        engines.append("rapidocr")
        logger.debug("RapidOCR detected")
    except ImportError:
        logger.debug("RapidOCR not available")

    # Check for MinerU (magic-pdf command or MINERU_COMMAND env var)
    if shutil.which("magic-pdf") or os.getenv("MINERU_COMMAND"):
        engines.append("mineru")
        logger.debug("MinerU detected")
    else:
        logger.debug("MinerU not available")

    # PDF text extraction is always available (uses PyMuPDF)
    engines.append("pdf_text")

    return engines


def get_default_ocr_engine() -> OCREngine:
    """
    Get the default OCR engine based on availability.

    Priority order:
    1. MinerU (most accurate, but optional)
    2. RapidOCR (good balance, built-in)
    3. PDF text extraction (fallback, always available)

    Returns:
        Name of the default OCR engine to use
    """
    available = detect_available_ocr_engines()

    # Prefer MinerU if available
    if "mineru" in available:
        logger.info("Using MinerU as default OCR engine")
        return "mineru"

    # Fall back to RapidOCR
    if "rapidocr" in available:
        logger.info("Using RapidOCR as default OCR engine")
        return "rapidocr"

    # Last resort: PDF text extraction
    logger.info("Using PDF text extraction as default OCR engine")
    return "pdf_text"


def validate_ocr_engine(engine: str) -> bool:
    """
    Validate that the specified OCR engine is available.

    Args:
        engine: OCR engine name to validate

    Returns:
        True if the engine is available, False otherwise
    """
    available = detect_available_ocr_engines()
    is_valid = engine in available

    if not is_valid:
        logger.warning(
            f"OCR engine '{engine}' is not available. "
            f"Available engines: {', '.join(available)}"
        )

    return is_valid


def get_ocr_engine_info(engine: OCREngine) -> dict[str, str]:
    """
    Get information about an OCR engine.

    Args:
        engine: OCR engine name

    Returns:
        Dictionary with engine information
    """
    info = {
        "mineru": {
            "name": "MinerU",
            "description": "High-accuracy OCR with layout analysis",
            "command": "magic-pdf",
            "optional": "true",
        },
        "rapidocr": {
            "name": "RapidOCR",
            "description": "Fast ONNX-based OCR engine",
            "package": "rapidocr-onnxruntime",
            "optional": "false",
        },
        "pdf_text": {
            "name": "PDF Text Extraction",
            "description": "Basic text extraction from PDF",
            "package": "PyMuPDF",
            "optional": "false",
        },
    }

    return info.get(engine, {"name": "Unknown", "description": "Unknown engine"})


def get_ocr_capabilities() -> dict[str, dict[str, bool]]:
    """
    Get capabilities of each available OCR engine.

    Returns:
        Dictionary mapping engine names to their capabilities
    """
    available = detect_available_ocr_engines()

    capabilities = {
        "mineru": {
            "layout_analysis": True,
            "table_detection": True,
            "formula_recognition": True,
            "multi_language": True,
            "available": "mineru" in available,
        },
        "rapidocr": {
            "layout_analysis": False,
            "table_detection": False,
            "formula_recognition": False,
            "multi_language": True,
            "available": "rapidocr" in available,
        },
        "pdf_text": {
            "layout_analysis": False,
            "table_detection": False,
            "formula_recognition": False,
            "multi_language": False,
            "available": True,  # Always available
        },
    }

    return capabilities
