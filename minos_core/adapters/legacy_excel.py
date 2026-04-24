"""Legacy Excel seed workbook converter.

The converter intentionally uses only Python's standard library so it can run
before optional Excel dependencies are installed. It reads OpenXML parts
directly, normalizes the three legacy workbook shapes, and writes the standard
MINOS-CORE fixture triplet.
"""

from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ..quality_matching import overlap_score, quality_tokens


SCHEMA_VERSION = "minos-core.fixture.v1"


@dataclass(frozen=True)
class Worksheet:
    name: str
    rows: dict[int, dict[str, str]]


@dataclass(frozen=True)
class Workbook:
    sheets: dict[str, Worksheet]


PROFILES: dict[str, dict[str, Any]] = {
    "door_hinge": {
        "process_flow": {
            "sheets": ["过程流程图"],
            "start": 8,
            "end": 24,
            "step": "A",
            "operation": "A",
            "function": ["F"],
            "special": ["H", "K"],
        },
        "pfmea": {
            "sheets": ["PFMEA"],
            "start": 16,
            "end": 58,
            "step": "A",
            "function": ["A"],
            "failure_mode": "B",
            "effect": "D",
            "severity": "F",
            "classification": "G",
            "cause": "H",
            "occurrence": "I",
            "prevention": "J",
            "detection_control": "K",
            "detection": "L",
            "action_priority": "",
            "inherit": ["A"],
        },
        "control_plan": {
            "sheets": ["控制计划"],
            "start": 16,
            "end": 57,
            "step": "A",
            "operation": "B",
            "characteristic": ["E", "F"],
            "classification": "G",
            "specification": "H",
            "measurement": "I",
            "sample_size": "J",
            "sample_frequency": "K",
            "control_method": "L",
            "reaction_plan": "N",
            "inherit": ["A", "B"],
        },
    },
    "limiter": {
        "process_flow": {
            "sheets": ["4过程流程图", "过程流程图"],
            "start": 10,
            "end": 34,
            "step": "A",
            "operation": "B",
            "function": ["G"],
            "special": ["H", "I", "J", "K"],
        },
        "pfmea": {
            "sheets": ["6PFMEA", "PFMEA"],
            "start": 10,
            "end": 71,
            "step": "B",
            "function": ["D", "E", "F"],
            "failure_mode": "I",
            "effect": "G",
            "severity": "H",
            "classification": "P",
            "cause": "J",
            "occurrence": "L",
            "prevention": "K",
            "detection_control": "M",
            "detection": "N",
            "action_priority": "O",
            "inherit": ["B", "D", "E", "F"],
        },
        "control_plan": {
            "sheets": ["7控制计划-过程", "控制计划"],
            "start": 12,
            "end": 81,
            "step": "A",
            "operation": "B",
            "characteristic": ["I", "L"],
            "classification": "O",
            "specification": "Q",
            "measurement": "U",
            "sample_size": "Y",
            "sample_frequency": "Z",
            "control_method": "AB",
            "reaction_plan": "AE",
            "inherit": ["A", "B"],
        },
    },
    "stamping": {
        "process_flow": {
            "sheets": ["7 过程流程图", "过程流程图"],
            "start": 9,
            "end": 20,
            "step": "A",
            "operation": "A",
            "function": ["A"],
            "special": ["I", "J", "K"],
        },
        "pfmea": {
            "sheets": ["8 PFMEA", "PFMEA"],
            "start": 16,
            "end": 69,
            "step": "A",
            "function": ["B"],
            "failure_mode": "C",
            "effect": "D",
            "severity": "E",
            "classification": "F",
            "cause": "G",
            "occurrence": "H",
            "prevention": "I",
            "detection_control": "J",
            "detection": "K",
            "action_priority": "",
            "inherit": ["A", "B"],
        },
        "control_plan": {
            "sheets": ["9 控制计划", "控制计划"],
            "start": 13,
            "end": 70,
            "step": "A",
            "operation": "B",
            "characteristic": ["F", "G", "H"],
            "classification": "I",
            "specification": "J",
            "measurement": "K",
            "sample_size": "L",
            "sample_frequency": "M",
            "control_method": "N",
            "reaction_plan": "O",
            "inherit": ["A", "B", "C"],
        },
    },
}


PROFILE_ALIASES = {
    "door-hinge": "door_hinge",
    "doorhinge": "door_hinge",
    "hinge": "door_hinge",
    "limit": "limiter",
    "door_limiter": "limiter",
    "check_limiter": "limiter",
    "press": "stamping",
    "stamp": "stamping",
}


def convert_legacy_workbook(
    xlsx_path: str | Path,
    output_dir: str | Path,
    sample_id: str | None = None,
    display_name: str | None = None,
    profile: str | None = None,
) -> dict[str, Path]:
    """Convert a legacy seed workbook into the standard fixture JSON triplet."""

    workbook = read_workbook(xlsx_path)
    sample_id = sample_id or _infer_sample_id(xlsx_path, profile)
    profile_name = _resolve_profile(workbook, sample_id, profile)
    display_name = display_name or _display_name_from_profile(profile_name)
    spec = PROFILES[profile_name]
    product = {
        "sample_id": sample_id,
        "part_number": sample_id.upper().replace("-", "_"),
        "part_name": display_name,
        "revision": "",
        "phase": "legacy-converted",
    }

    steps = _parse_process_flow(workbook, spec["process_flow"])
    failures = _parse_pfmea(workbook, spec["pfmea"])
    controls = _parse_control_plan(workbook, spec["control_plan"])
    steps = _reconcile_process_steps(steps, failures)
    _link_controls(failures, controls)

    process_flow = {
        "document_type": "process_flow",
        "schema_version": SCHEMA_VERSION,
        "product": product,
        "steps": steps,
        "links": _process_links(steps),
    }
    pfmea = {
        "document_type": "pfmea",
        "schema_version": SCHEMA_VERSION,
        "product": product,
        "rows": failures,
    }
    control_plan = {
        "document_type": "control_plan",
        "schema_version": SCHEMA_VERSION,
        "product": product,
        "rows": controls,
    }

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "process_flow": destination / "process_flow.json",
        "pfmea": destination / "pfmea.json",
        "control_plan": destination / "control_plan.json",
    }
    _write_json(paths["process_flow"], process_flow)
    _write_json(paths["pfmea"], pfmea)
    _write_json(paths["control_plan"], control_plan)
    return paths


def read_workbook(path: str | Path) -> Workbook:
    xlsx_path = Path(path)
    with zipfile.ZipFile(xlsx_path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_targets = _read_sheet_targets(archive)
        sheets = {}
        for sheet_name, target in sheet_targets:
            rows = _read_sheet_rows(archive, target, shared_strings)
            sheets[sheet_name] = Worksheet(sheet_name, rows)
    return Workbook(sheets)


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root:
        texts = [
            node.text or "" for node in item.iter() if _local_name(node.tag) == "t"
        ]
        values.append(_clean("".join(texts)))
    return values


def _read_sheet_targets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: _normalize_part_path("xl", rel.attrib["Target"])
        for rel in rels
        if "Id" in rel.attrib and "Target" in rel.attrib
    }
    sheets: list[tuple[str, str]] = []
    for sheet in workbook.iter():
        if _local_name(sheet.tag) != "sheet":
            continue
        rel_id = sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        if rel_id and rel_id in rel_targets:
            sheets.append((sheet.attrib.get("name", ""), rel_targets[rel_id]))
    return sheets


def _read_sheet_rows(
    archive: zipfile.ZipFile,
    part_name: str,
    shared_strings: list[str],
) -> dict[int, dict[str, str]]:
    root = ET.fromstring(archive.read(part_name))
    rows: dict[int, dict[str, str]] = defaultdict(dict)

    for cell in root.iter():
        if _local_name(cell.tag) != "c":
            continue
        ref = cell.attrib.get("r", "")
        row_index, column = _split_cell_ref(ref)
        if row_index <= 0 or not column:
            continue
        value = _cell_value(cell, shared_strings)
        if value:
            rows[row_index][column] = value

    for merge_ref in _merge_refs(root):
        start_row, start_col, end_row, end_col = _parse_range(merge_ref)
        if start_row <= 0 or end_row < start_row or end_col < start_col:
            continue
        source = rows.get(start_row, {}).get(_column_name(start_col), "")
        if not source:
            continue
        if end_row - start_row > 500 or end_col - start_col > 100:
            continue
        for row_index in range(start_row, end_row + 1):
            row = rows[row_index]
            for col_index in range(start_col, end_col + 1):
                row.setdefault(_column_name(col_index), source)
    return dict(rows)


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return _clean(
            "".join(
                node.text or "" for node in cell.iter() if _local_name(node.tag) == "t"
            )
        )

    raw = ""
    for child in cell:
        if _local_name(child.tag) == "v":
            raw = child.text or ""
            break
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return ""
    return _clean(raw)


def _merge_refs(root: ET.Element) -> list[str]:
    refs: list[str] = []
    for node in root.iter():
        if _local_name(node.tag) == "mergeCell" and node.attrib.get("ref"):
            refs.append(node.attrib["ref"])
    return refs


def _parse_process_flow(
    workbook: Workbook, spec: dict[str, Any]
) -> list[dict[str, Any]]:
    sheet = _select_sheet(workbook, spec["sheets"], "process_flow")
    steps: list[dict[str, Any]] = []
    generated_index = 1
    for row_index, row in _data_rows(sheet, spec):
        step_text = _value(row, spec["step"])
        if not _is_data_text(step_text):
            continue
        step_id = _step_id(step_text, generated_index)
        sequence = _sequence_from_id(step_id, generated_index * 10)
        operation = _first_nonempty(
            _operation_from_step(step_text),
            _combine(row, spec.get("operation", [])),
            f"Legacy process step {sequence}",
        )
        function = _combine(row, spec.get("function", [])) or operation
        steps.append(
            {
                "process_step_id": step_id,
                "sequence": sequence,
                "operation": operation,
                "process_function": function,
                "owner": "",
                "input_refs": [],
                "output_refs": [],
                "special_characteristics": _unique(
                    _values(row, spec.get("special", []))
                ),
                "source_row": row_index,
            }
        )
        generated_index += 1
    return _dedupe_steps(steps)


def _parse_pfmea(workbook: Workbook, spec: dict[str, Any]) -> list[dict[str, Any]]:
    sheet = _select_sheet(workbook, spec["sheets"], "pfmea")
    state: dict[str, str] = {}
    counters: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    generated_index = 1
    for row_index, row in _data_rows(sheet, spec):
        _update_state(state, row, spec.get("inherit", []))
        failure_mode = _value(row, spec["failure_mode"])
        if not _is_data_text(failure_mode):
            continue
        step_text = state.get(spec["step"], "") or _value(row, spec["step"])
        step_id = _step_id(step_text, generated_index)
        counters[step_id] += 1
        severity = _integer(_value(row, spec["severity"]))
        classification = _value(row, spec["classification"])
        action_priority = _value(row, spec.get("action_priority", ""))
        if not action_priority and (classification or severity >= 9):
            action_priority = "H" if severity >= 9 else "M"
        item = {
            "pfmea_id": _make_id("PFMEA", step_id, counters[step_id]),
            "process_step_id": step_id,
            "process_function": _combine_with_state(
                row, state, spec.get("function", [])
            ),
            "failure_mode": failure_mode,
            "failure_effect": _value(row, spec["effect"]),
            "severity": severity,
            "failure_cause": _value(row, spec["cause"]),
            "occurrence": _integer(_value(row, spec["occurrence"])),
            "prevention_control": _value(row, spec["prevention"]),
            "detection_control": _value(row, spec["detection_control"]),
            "detection": _integer(_value(row, spec["detection"])),
            "action_priority": action_priority,
            "classification": classification,
            "linked_control_plan_id": "",
            "source_row": row_index,
        }
        rows.append(item)
        generated_index += 1
    return rows


def _parse_control_plan(
    workbook: Workbook, spec: dict[str, Any]
) -> list[dict[str, Any]]:
    sheet = _select_sheet(workbook, spec["sheets"], "control_plan")
    state: dict[str, str] = {}
    counters: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    generated_index = 1
    for row_index, row in _data_rows(sheet, spec):
        _update_state(state, row, spec.get("inherit", []))
        characteristic = _combine(row, spec.get("characteristic", []))
        if not _is_data_text(characteristic) and not _has_any(
            row, spec, ["specification", "measurement", "control_method"]
        ):
            continue
        step_text = state.get(spec["step"], "") or _value(row, spec["step"])
        step_id = _step_id(step_text, generated_index)
        counters[step_id] += 1
        rows.append(
            {
                "control_plan_id": _make_id("CP", step_id, counters[step_id]),
                "process_step_id": step_id,
                "pfmea_id": "",
                "product_process_characteristic": characteristic,
                "specification": _value(row, spec["specification"]),
                "classification": _value(row, spec["classification"]),
                "measurement_method": _value(row, spec["measurement"]),
                "sample_size": _value(row, spec["sample_size"]),
                "sample_frequency": _value(row, spec["sample_frequency"]),
                "control_method": _value(row, spec["control_method"]),
                "reaction_plan": _value(row, spec["reaction_plan"]),
                "source_row": row_index,
            }
        )
        generated_index += 1
    return rows


def _reconcile_process_steps(
    steps: list[dict[str, Any]], failures: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not failures:
        return steps
    steps_by_id = {step["process_step_id"]: step for step in steps}
    ordered_failure_steps = _unique(
        [failure["process_step_id"] for failure in failures]
    )
    reconciled: list[dict[str, Any]] = []
    for index, step_id in enumerate(ordered_failure_steps, start=1):
        if step_id in steps_by_id:
            reconciled.append(steps_by_id[step_id])
            continue
        first_failure = next(
            item for item in failures if item["process_step_id"] == step_id
        )
        reconciled.append(
            {
                "process_step_id": step_id,
                "sequence": _sequence_from_id(step_id, index * 10),
                "operation": first_failure.get("process_function")
                or f"Legacy process step {step_id}",
                "process_function": first_failure.get("process_function", ""),
                "owner": "",
                "input_refs": [],
                "output_refs": [],
                "special_characteristics": _unique(
                    [
                        item.get("classification", "")
                        for item in failures
                        if item["process_step_id"] == step_id
                    ]
                ),
            }
        )
    return sorted(
        reconciled,
        key=lambda item: (int(item.get("sequence", 0) or 0), item["process_step_id"]),
    )


def _link_controls(
    failures: list[dict[str, Any]], controls: list[dict[str, Any]]
) -> None:
    controls_by_step: dict[str, list[dict[str, Any]]] = defaultdict(list)
    failures_by_step: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for control in controls:
        controls_by_step[control["process_step_id"]].append(control)
    for failure in failures:
        failures_by_step[failure["process_step_id"]].append(failure)

    for step_id, step_controls in controls_by_step.items():
        step_failures = failures_by_step.get(step_id, [])
        used: set[str] = set()
        linked_controls: set[str] = set()
        scored_pairs = sorted(
            (
                (_link_score(failure, control), failure, control)
                for failure in step_failures
                for control in step_controls
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        for score, failure, control in scored_pairs:
            if score <= 0:
                break
            if (
                failure["pfmea_id"] in used
                or control["control_plan_id"] in linked_controls
            ):
                continue
            control["pfmea_id"] = failure["pfmea_id"]
            failure["linked_control_plan_id"] = control["control_plan_id"]
            used.add(failure["pfmea_id"])
            linked_controls.add(control["control_plan_id"])

    all_controls = controls[:]
    for failure in failures:
        if not _is_mandatory_failure(failure):
            continue
        candidates = _candidate_controls_for_failure(
            failure, controls_by_step, all_controls
        )
        if candidates:
            matched_control = _preferred_existing_control(
                failure, candidates
            ) or _best_control_match(failure, candidates)
            failure["linked_control_plan_id"] = matched_control["control_plan_id"]
            _ensure_reverse_pfmea_link(failure, matched_control, controls)


def _best_failure_match(
    control: dict[str, Any],
    failures: list[dict[str, Any]],
    used: set[str],
) -> dict[str, Any] | None:
    available = [failure for failure in failures if failure["pfmea_id"] not in used]
    if not available:
        return None
    scored = sorted(
        available, key=lambda failure: _link_score(failure, control), reverse=True
    )
    return scored[0] if _link_score(scored[0], control) > 0 else None


def _best_control_match(
    failure: dict[str, Any], controls: list[dict[str, Any]]
) -> dict[str, Any]:
    return sorted(
        controls,
        key=lambda control: (
            _link_score(failure, control),
            not bool(control.get("pfmea_id")),
        ),
        reverse=True,
    )[0]


def _preferred_existing_control(
    failure: dict[str, Any], controls: list[dict[str, Any]]
) -> dict[str, Any] | None:
    linked_control_id = failure.get("linked_control_plan_id", "")
    if not linked_control_id:
        return None
    return next(
        (
            control
            for control in controls
            if control["control_plan_id"] == linked_control_id
        ),
        None,
    )


def _candidate_controls_for_failure(
    failure: dict[str, Any],
    controls_by_step: dict[str, list[dict[str, Any]]],
    all_controls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    same_step = controls_by_step.get(failure["process_step_id"], [])
    if _can_match_across_steps(failure):
        cross_step = [
            control for control in all_controls if _link_score(failure, control) >= 4
        ]
        return cross_step or same_step or all_controls
    return same_step or all_controls


def _can_match_across_steps(failure: dict[str, Any]) -> bool:
    classification = str(failure.get("classification", "")).upper()
    if classification in {"SC", "CC"}:
        return True
    terms = _search_text(
        failure.get("process_function", ""),
        failure.get("failure_mode", ""),
        failure.get("failure_effect", ""),
        failure.get("failure_cause", ""),
    )
    return bool({"restricted_substance", "torque"} & terms)


def _ensure_reverse_pfmea_link(
    failure: dict[str, Any],
    control: dict[str, Any],
    controls: list[dict[str, Any]],
) -> None:
    pfmea_id = failure["pfmea_id"]
    if any(item.get("pfmea_id") == pfmea_id for item in controls):
        return
    if not control.get("pfmea_id"):
        control["pfmea_id"] = pfmea_id
        return
    duplicate = dict(control)
    duplicate["control_plan_id"] = _derived_control_id(
        control["control_plan_id"], pfmea_id, controls
    )
    duplicate["pfmea_id"] = pfmea_id
    duplicate["derived_from_control_plan_id"] = control["control_plan_id"]
    controls.append(duplicate)
    failure["linked_control_plan_id"] = duplicate["control_plan_id"]


def _derived_control_id(
    base_id: str, pfmea_id: str, controls: list[dict[str, Any]]
) -> str:
    suffix = pfmea_id.replace("PFMEA-", "")
    candidate = f"{base_id}-{suffix}"
    existing = {control.get("control_plan_id", "") for control in controls}
    if candidate not in existing:
        return candidate
    index = 2
    while f"{candidate}-{index}" in existing:
        index += 1
    return f"{candidate}-{index}"


def _link_score(failure: dict[str, Any], control: dict[str, Any]) -> int:
    failure_terms = _search_text(
        failure.get("classification", ""),
        failure.get("process_function", ""),
        failure.get("failure_mode", ""),
        failure.get("failure_cause", ""),
        failure.get("detection_control", ""),
    )
    control_terms = _search_text(
        control.get("classification", ""),
        control.get("product_process_characteristic", ""),
        control.get("specification", ""),
        control.get("measurement_method", ""),
        control.get("control_method", ""),
    )
    score = _overlap_score(failure_terms, control_terms)
    failure_class = str(failure.get("classification", "")).upper()
    control_class = str(control.get("classification", "")).upper()
    if failure_class and failure_class == control_class:
        score += 20
    elif failure_class and control_class and failure_class != control_class:
        score -= 4
    if failure.get("process_step_id") == control.get("process_step_id"):
        score += 2
    return score


def _resolve_profile(workbook: Workbook, sample_id: str, profile: str | None) -> str:
    candidates = [profile or "", sample_id]
    for candidate in candidates:
        key = _profile_key(candidate)
        if key in PROFILES:
            return key
    sheet_names = " ".join(workbook.sheets)
    normalized = _compact(sheet_names)
    if "门铰链" in sheet_names or "过程流程图pfmea控制计划" in normalized:
        return "door_hinge"
    if "7控制计划过程" in normalized or "限位" in sheet_names:
        return "limiter"
    if "9控制计划" in normalized or "冲压" in sheet_names:
        return "stamping"
    raise ValueError(f"unsupported legacy Excel profile: {profile or sample_id}")


def _infer_sample_id(xlsx_path: str | Path, profile: str | None) -> str:
    if profile:
        return _profile_key(profile)
    name = str(Path(xlsx_path).name)
    if "门铰链" in name or "hinge" in name.lower():
        return "door_hinge"
    if "冲压" in name or "stamp" in name.lower():
        return "stamping"
    if "限位" in name or "limit" in name.lower():
        return "limiter"
    return Path(xlsx_path).stem


def _display_name_from_profile(profile_name: str) -> str:
    return {
        "door_hinge": "门铰链",
        "stamping": "冲压件",
        "limiter": "限位器",
    }.get(profile_name, profile_name)


def _profile_key(value: str) -> str:
    key = _compact(value).lower().replace("-", "_")
    return PROFILE_ALIASES.get(key, key)


def _select_sheet(workbook: Workbook, names: list[str], kind: str) -> Worksheet:
    normalized = {_compact(name): sheet for name, sheet in workbook.sheets.items()}
    for candidate in names:
        compact_candidate = _compact(candidate)
        for sheet_name, sheet in normalized.items():
            if compact_candidate and compact_candidate in sheet_name:
                return sheet
    for name, sheet in workbook.sheets.items():
        compact = _compact(name).lower()
        if kind == "process_flow" and ("过程流程" in compact or "flow" in compact):
            return sheet
        if kind == "pfmea" and "pfmea" in compact:
            return sheet
        if kind == "control_plan" and (
            "控制计划" in compact or "controlplan" in compact
        ):
            return sheet
    raise ValueError(
        f"cannot find {kind} sheet; available sheets: {', '.join(workbook.sheets)}"
    )


def _data_rows(
    sheet: Worksheet, spec: dict[str, Any]
) -> list[tuple[int, dict[str, str]]]:
    start = int(spec.get("start", 1))
    end = int(spec.get("end") or max(sheet.rows or {0: {}}))
    return [(index, sheet.rows.get(index, {})) for index in range(start, end + 1)]


def _update_state(
    state: dict[str, str], row: dict[str, str], columns: list[str]
) -> None:
    for column in columns:
        value = _value(row, column)
        if value:
            state[column] = value


def _combine_with_state(
    row: dict[str, str], state: dict[str, str], columns: list[str]
) -> str:
    values = []
    for column in columns:
        values.append(_value(row, column) or state.get(column, ""))
    return "；".join(_unique([value for value in values if value]))


def _combine(row: dict[str, str], columns: str | list[str]) -> str:
    return "；".join(_unique(_values(row, columns)))


def _values(row: dict[str, str], columns: str | list[str]) -> list[str]:
    if isinstance(columns, str):
        columns = [columns]
    return [_value(row, column) for column in columns if _value(row, column)]


def _value(row: dict[str, str], column: str) -> str:
    if not column:
        return ""
    return _clean(row.get(column, ""))


def _has_any(row: dict[str, str], spec: dict[str, Any], keys: list[str]) -> bool:
    return any(_value(row, spec[key]) for key in keys if spec.get(key))


def _process_links(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    links = []
    for left, right in zip(steps, steps[1:]):
        links.append({"from": left["process_step_id"], "to": right["process_step_id"]})
    return links


def _dedupe_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for step in steps:
        step_id = step["process_step_id"]
        if step_id in seen:
            continue
        seen.add(step_id)
        result.append(step)
    return result


def _step_id(text: str, fallback_index: int) -> str:
    match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", text or "")
    if match:
        number = int(match.group(1))
        width = 2 if number < 100 else 3
        return f"P{number:0{width}d}"
    return f"P{fallback_index * 10:02d}"


def _sequence_from_id(step_id: str, default: int) -> int:
    match = re.search(r"\d+", step_id)
    return int(match.group(0)) if match else default


def _make_id(prefix: str, step_id: str, counter: int) -> str:
    return f"{prefix}-{step_id}-{counter:03d}"


def _operation_from_step(text: str) -> str:
    return _clean(re.sub(r"^\s*\d+\s*[-_.、:]?\s*", "", text or ""))


def _is_data_text(text: str) -> bool:
    value = _clean(text)
    if not value:
        return False
    upper = value.upper()
    noise = ("END", "PFMEA", "控制计划", "过程流程", "编号", "项目", "日期", "表单")
    return not any(item in upper for item in noise)


def _is_mandatory_failure(failure: dict[str, Any]) -> bool:
    return (
        int(failure.get("severity", 0) or 0) >= 9
        or bool(str(failure.get("classification", "")).strip())
        or str(failure.get("action_priority", "")).upper() in {"H", "M"}
    )


def _integer(value: str) -> int:
    match = re.search(r"-?\d+", value or "")
    return int(match.group(0)) if match else 0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _first_nonempty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def _search_text(*values: str) -> set[str]:
    return quality_tokens(*values)


def _overlap_score(left: set[str], right: set[str]) -> int:
    return overlap_score(left, right)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", "\n")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalize_part_path(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    parts = []
    for part in f"{base}/{target}".split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _split_cell_ref(ref: str) -> tuple[int, str]:
    match = re.match(r"([A-Z]+)(\d+)", ref or "")
    if not match:
        return 0, ""
    return int(match.group(2)), match.group(1)


def _parse_range(ref: str) -> tuple[int, int, int, int]:
    parts = ref.split(":")
    if len(parts) == 1:
        parts.append(parts[0])
    start_row, start_col = _cell_position(parts[0])
    end_row, end_col = _cell_position(parts[1])
    return start_row, start_col, end_row, end_col


def _cell_position(ref: str) -> tuple[int, int]:
    row, column = _split_cell_ref(ref)
    return row, _column_index(column)


def _column_index(column: str) -> int:
    index = 0
    for char in column:
        index = index * 26 + ord(char) - ord("A") + 1
    return index


def _column_name(index: int) -> str:
    chars = []
    while index:
        index, remainder = divmod(index - 1, 26)
        chars.append(chr(ord("A") + remainder))
    return "".join(reversed(chars))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
