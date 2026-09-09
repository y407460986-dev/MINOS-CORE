"""Safe demo drawing and acceptance helpers for desktop trial runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

REQUIRED_THREE_TABLE_EXPORTS = (
    "unified_workbook",
    "process_flow",
    "pfmea",
    "control_plan",
)


@dataclass(frozen=True)
class WorkbookZipCheck:
    path: str
    ok: bool
    errors: tuple[str, ...] = ()
    worksheets: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThreeTableAcceptanceSummary:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    workbook_checks: dict[str, WorkbookZipCheck] = field(default_factory=dict)


def write_safe_demo_drawing_png(path: str | Path) -> Path:
    """Create a synthetic demo drawing PNG without customer information."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("safe demo PNG generation requires Pillow") from exc

    image = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(image)
    ink = (30, 35, 40)
    light = (185, 195, 205)
    accent = (15, 94, 156)

    draw.rectangle((40, 40, 1360, 860), outline=ink, width=3)
    draw.rectangle((70, 90, 900, 620), outline=ink, width=4)
    draw.rectangle((210, 190, 760, 500), outline=ink, width=5)
    draw.line((210, 345, 760, 345), fill=light, width=2)
    draw.line((485, 190, 485, 500), fill=light, width=2)
    for cx, cy in ((300, 280), (670, 280), (300, 420), (670, 420)):
        draw.ellipse((cx - 35, cy - 35, cx + 35, cy + 35), outline=ink, width=4)
        draw.line((cx - 55, cy, cx + 55, cy), fill=light, width=1)
        draw.line((cx, cy - 55, cx, cy + 55), fill=light, width=1)

    draw.line((300, 565, 670, 565), fill=accent, width=3)
    draw.line((300, 545, 300, 585), fill=accent, width=3)
    draw.line((670, 545, 670, 585), fill=accent, width=3)
    draw.text((420, 580), "370.0 +/-0.20", fill=accent)
    draw.text((790, 255), "4X DIA 10.0 +/-0.05", fill=accent)
    draw.line((720, 285, 670, 280), fill=accent, width=2)
    draw.text((790, 315), "SC-01 POSITION +/-0.10", fill=accent)
    draw.line((720, 340, 670, 420), fill=accent, width=2)

    title_x = 950
    draw.rectangle((930, 90, 1330, 620), outline=ink, width=2)
    title_rows = [
        ("PART NAME", "DEMO BRACKET"),
        ("DRAWING NO.", "MINOS-DEMO-001"),
        ("REV", "A"),
        ("MATERIAL", "SPCC-SD 1.6 mm"),
        ("SURFACE", "ZINC PLATED"),
        ("GENERAL TOL.", "+/-0.20 mm"),
        ("SPECIAL CHAR.", "SC-01 HOLE POSITION"),
    ]
    y = 115
    for label, value in title_rows:
        draw.text((title_x, y), label, fill=ink)
        draw.text((title_x + 135, y), value, fill=ink)
        draw.line((940, y + 28, 1320, y + 28), fill=light, width=1)
        y += 58

    notes = [
        "PROCESS CLUES: BLANKING -> PIERCING -> DEBURR -> PLATING -> INSPECTION",
        "TECH REQ: NO SHARP BURRS; CRITICAL HOLES REQUIRE 100% GO/NOGO CHECK",
        "DEMO ONLY: SYNTHETIC DRAWING, NO CUSTOMER DATA",
    ]
    y = 675
    for note in notes:
        draw.text((80, y), note, fill=ink)
        y += 44

    image.save(target, format="PNG")
    return target


def check_xlsx_zip_openable(path: str | Path) -> WorkbookZipCheck:
    """Check that an xlsx file is a readable OpenXML zip workbook."""

    workbook_path = Path(path)
    errors: list[str] = []
    worksheets: list[str] = []
    if not workbook_path.exists():
        return WorkbookZipCheck(str(workbook_path), False, ("workbook file is missing",))
    if not workbook_path.is_file():
        return WorkbookZipCheck(str(workbook_path), False, ("workbook path is not a file",))
    try:
        with ZipFile(workbook_path) as archive:
            broken_member = archive.testzip()
            names = set(archive.namelist())
            worksheets = sorted(
                name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            )
    except BadZipFile as exc:
        return WorkbookZipCheck(str(workbook_path), False, (f"workbook is not a valid zip: {exc}",))

    if broken_member:
        errors.append(f"workbook zip member is corrupt: {broken_member}")
    for required in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"):
        if required not in names:
            errors.append(f"workbook is missing {required}")
    if not worksheets:
        errors.append("workbook has no worksheet xml files")
    return WorkbookZipCheck(str(workbook_path), not errors, tuple(errors), tuple(worksheets))


def check_three_table_workbook_exports(result: dict[str, Any]) -> dict[str, WorkbookZipCheck]:
    """Run xlsx zip checks for the unified workbook and three split exports."""

    exports = result.get("exports") if isinstance(result, dict) else {}
    checks: dict[str, WorkbookZipCheck] = {}
    for key in REQUIRED_THREE_TABLE_EXPORTS:
        value = exports.get(key) if isinstance(exports, dict) else None
        if not value:
            checks[key] = WorkbookZipCheck("", False, (f"exports.{key} is missing",))
            continue
        checks[key] = check_xlsx_zip_openable(value)
    return checks


def summarize_three_table_acceptance(result: dict[str, Any]) -> ThreeTableAcceptanceSummary:
    """Validate the delivery shape of a generate-three-tables result."""

    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(result, dict):
        return ThreeTableAcceptanceSummary(False, ("result must be a dict",))

    if result.get("document_type") != "three_table_generation_result":
        errors.append("document_type must be three_table_generation_result")

    manifest = result.get("manifest")
    if not isinstance(manifest, dict) or not manifest:
        errors.append("manifest must be a non-empty object")
    else:
        manifest_path = str(manifest.get("path", "")).strip()
        if not manifest_path:
            errors.append("manifest.path is missing")
        elif not Path(manifest_path).exists():
            errors.append("manifest.path does not exist")
        artifact_hashes = manifest.get("artifact_hashes")
        if not isinstance(artifact_hashes, dict) or not artifact_hashes:
            errors.append("manifest.artifact_hashes must be a non-empty object")

    exports = result.get("exports")
    if not isinstance(exports, dict):
        errors.append("exports must be an object")
    else:
        for key in REQUIRED_THREE_TABLE_EXPORTS:
            if not str(exports.get(key, "")).strip():
                errors.append(f"exports.{key} is missing")

    _require_drawing_analysis_evidence(result.get("drawing_analysis"), errors)
    _require_rows(result.get("process_flow"), ("steps", "process_steps"), "process_flow", errors)
    _require_rows(result.get("pfmea"), ("rows", "failure_modes"), "pfmea", errors)
    _require_rows(result.get("control_plan"), ("rows", "controls"), "control_plan", errors)

    manual_review = result.get("manual_review")
    if not isinstance(manual_review, dict):
        errors.append("manual_review must be an object")
    else:
        if not isinstance(manual_review.get("required"), bool):
            errors.append("manual_review.required must be boolean")
        if not isinstance(manual_review.get("items"), list):
            errors.append("manual_review.items must be a list")

    raw_warnings = result.get("warnings")
    if not isinstance(raw_warnings, list):
        errors.append("warnings must be a list")
    else:
        warnings.extend(str(item) for item in raw_warnings)

    workbook_checks = check_three_table_workbook_exports(result)
    for key, check in workbook_checks.items():
        if not check.ok:
            errors.extend(f"{key}: {message}" for message in check.errors)

    return ThreeTableAcceptanceSummary(
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        workbook_checks=workbook_checks,
    )


def _require_drawing_analysis_evidence(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("drawing_analysis must be an object")
        return
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("drawing_analysis.evidence must be a non-empty list")
        return
    evidence_ids = {
        str(item.get("evidence_id"))
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id")
    }
    refs = sorted(_collect_evidence_refs(value))
    if not refs:
        errors.append("drawing_analysis must include evidence_refs")
        return
    unknown_refs = [ref for ref in refs if ref not in evidence_ids]
    if unknown_refs:
        errors.append("drawing_analysis has unknown evidence_refs: " + ", ".join(unknown_refs))


def _require_rows(value: Any, field_names: tuple[str, ...], label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    for field_name in field_names:
        rows = value.get(field_name)
        if isinstance(rows, list) and rows:
            return
    errors.append(f"{label} must contain non-empty {' or '.join(field_names)}")


def _collect_evidence_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        raw_refs = value.get("evidence_refs")
        if isinstance(raw_refs, list):
            refs.update(str(ref) for ref in raw_refs if str(ref).strip())
        for item in value.values():
            refs.update(_collect_evidence_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_collect_evidence_refs(item))
    return refs
