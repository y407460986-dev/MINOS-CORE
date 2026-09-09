"""Type aliases and TypedDicts for common MINOS dict shapes.

These replace raw ``dict[str, Any]`` / ``Any`` return types in pipeline
functions, making data flow easier to follow and refactor.
"""
from __future__ import annotations

from typing import Any, TypedDict


class DrawingAnalysisResult(TypedDict, total=False):
    """Shape of a drawing analysis result."""
    drawing_identity: dict[str, Any] | None
    materials: list[dict[str, Any]]
    surface_treatments: list[dict[str, Any]]
    dimensions: list[dict[str, Any]]
    tolerances: list[dict[str, Any]]
    special_characteristics: list[dict[str, Any]]
    technical_requirements: list[dict[str, Any]]
    inspection_requirements: list[dict[str, Any]]
    manufacturing_clues: list[dict[str, Any]]
    uncertainties: list[dict[str, Any]]


class DrawingPage(TypedDict, total=False):
    """Shape of a rendered drawing page."""
    width: int
    height: int
    sha256: str


class QualityGateResult(TypedDict, total=False):
    """Shape of a quality gate evaluation."""
    gate_name: str
    can_continue: bool
    allow_user_export: bool
    errors: list[str]
    warnings: list[str]
