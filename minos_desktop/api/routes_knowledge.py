"""Knowledge rule routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, status

from minos_core._paths import user_data_dir
from minos_core.part_family_knowledge import (
    DEFAULT_FAMILY_NAMES,
    convert_seed_workbook_to_family_knowledge,
    load_part_family_index,
    load_part_family_knowledge,
)
from minos_core.validation import InputValidator, PathValidationError
from minos_desktop.services import DesktopKnowledgeStore

from .schemas import KnowledgeImportSeedsRequest, KnowledgeRuleRequest, failure_from_exception

router = APIRouter()

# Allowed base directories for knowledge file path traversal validation.
# A path is accepted if it resolves under any of these bases.
ALLOWED_KNOWLEDGE_BASES: tuple[Path, ...] = (
    (Path(__file__).resolve().parents[2] / "configs" / "knowledge").resolve(),
    user_data_dir().parent.resolve(),
)


def _validate_knowledge_path(path: Path) -> Path:
    """Validate a knowledge path is within an allowed base directory."""
    for base in ALLOWED_KNOWLEDGE_BASES:
        try:
            return InputValidator.validate_path_traversal(path, base)
        except PathValidationError:
            continue
    # Fallback: re-raise against the first base for a clear error message
    return InputValidator.validate_path_traversal(path, ALLOWED_KNOWLEDGE_BASES[0])


@router.get("/knowledge/rules")
def list_rules(request: Request, include_disabled: bool = False) -> list[dict[str, Any]]:
    return DesktopKnowledgeStore(request.app.state.db_path).list_rules(
        include_disabled=include_disabled
    )


@router.post("/knowledge/rules", status_code=status.HTTP_201_CREATED)
def add_rule(payload: KnowledgeRuleRequest, request: Request) -> dict[str, Any]:
    return DesktopKnowledgeStore(request.app.state.db_path).add_rule(
        rule_id=payload.rule_id,
        category=payload.category,
        title=payload.title or payload.rule_id,
        payload=payload.payload,
        enabled=payload.enabled,
    )


@router.delete("/knowledge/rules/{rule_id}")
def disable_rule(rule_id: str, request: Request) -> dict[str, Any]:
    return DesktopKnowledgeStore(request.app.state.db_path).disable_rule(rule_id)


@router.get("/knowledge/families")
def list_part_families() -> dict[str, Any]:
    index = load_part_family_index()
    families: list[dict[str, Any]] = []
    for entry in index.get("families", []):
        if not isinstance(entry, dict):
            continue
        family_key = str(entry.get("family_key", "")).strip()
        if not family_key:
            continue
        row: dict[str, Any] = {
            "family_key": family_key,
            "family_name": str(entry.get("family_name", family_key)),
            "knowledge_path": str(entry.get("knowledge_path", "")),
            "default_seed_dir": str(entry.get("default_seed_dir", "")),
            "default_seed_workbook": str(entry.get("default_seed_workbook", "")),
        }
        try:
            knowledge = load_part_family_knowledge(family_key)
            row.update(
                {
                    "available": True,
                    "process_route_template_count": len(
                        _items(knowledge.get("process_route_templates"))
                    ),
                    "pfmea_pattern_count": len(_items(knowledge.get("pfmea_patterns"))),
                    "control_plan_pattern_count": len(
                        _items(knowledge.get("control_plan_patterns"))
                    ),
                    "special_characteristic_pattern_count": len(
                        _items(knowledge.get("special_characteristic_patterns"))
                    ),
                    "source_ref_count": len(_items(knowledge.get("source_refs"))),
                }
            )
        except (FileNotFoundError, KeyError, ValueError, ImportError) as exc:
            row.update({"available": False, "failure_message": str(exc)})
        families.append(row)
    return {
        "schema_version": index.get("schema_version", ""),
        "families": families,
    }


@router.post("/knowledge/import-seeds")
def import_seed_knowledge(payload: KnowledgeImportSeedsRequest) -> dict[str, Any]:
    output_dir = (
        _validate_knowledge_path(Path(payload.output_dir).expanduser())
        if payload.output_dir
        else None
    )
    imported = []
    try:
        for family_key, seed_dir_str in payload.seed_dirs.items():
            default_name = DEFAULT_FAMILY_NAMES.get(family_key, family_key)
            seed_dir = _validate_knowledge_path(Path(seed_dir_str).expanduser())
            knowledge = convert_seed_workbook_to_family_knowledge(
                seed_dir,
                family_key,
                default_name,
            )
            output_path = ""
            if payload.write_files:
                target_dir = output_dir or (
                    Path(__file__).resolve().parents[2]
                    / "configs"
                    / "knowledge"
                    / "part_families"
                )
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{family_key}.json"
                target.write_text(
                    json.dumps(knowledge, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                output_path = str(target)
            imported.append(
                {
                    "family_key": knowledge.get("family_key", family_key),
                    "family_name": knowledge.get("family_name", default_name),
                    "source": str(seed_dir),
                    "output_path": output_path,
                    "process_route_template_count": len(
                        _items(knowledge.get("process_route_templates"))
                    ),
                    "pfmea_pattern_count": len(_items(knowledge.get("pfmea_patterns"))),
                    "control_plan_pattern_count": len(
                        _items(knowledge.get("control_plan_patterns"))
                    ),
                    "special_characteristic_pattern_count": len(
                        _items(knowledge.get("special_characteristic_patterns"))
                    ),
                    "source_ref_count": len(_items(knowledge.get("source_refs"))),
                }
            )
    except (FileNotFoundError, KeyError, ValueError, ImportError, OSError) as exc:
        raise failure_from_exception(exc) from exc
    return {
        "status": "ok",
        "write_files": payload.write_files,
        "output_dir": str(output_dir or ""),
        "families": imported,
    }


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
