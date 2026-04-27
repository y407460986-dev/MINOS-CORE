"""Domain Core business objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Product:
    sample_id: str = ""
    part_number: str = ""
    part_name: str = ""
    revision: str = ""
    phase: str = ""

    @classmethod
    def from_mapping(cls, data: Any) -> "Product":
        if isinstance(data, Product):
            return data
        if not isinstance(data, dict):
            return cls()
        return cls(
            sample_id=str(data.get("sample_id", "")),
            part_number=str(data.get("part_number", "")),
            part_name=str(data.get("part_name", "")),
            revision=str(data.get("revision", "")),
            phase=str(data.get("phase", "")),
        )


@dataclass
class ProcessStep:
    process_step_id: str
    sequence: int = 0
    operation: str = ""
    process_function: str = ""
    process_purpose: str = ""
    product_characteristics: list[str] = field(default_factory=list)
    process_characteristics: list[str] = field(default_factory=list)
    equipment: str = ""
    tooling: str = ""
    gauges: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    flow_type: str = ""
    owner: str = ""
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    special_characteristics: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    needs_confirmation: bool = False

    @property
    def id(self) -> str:
        return self.process_step_id

    @property
    def step_no(self) -> str:
        return self.process_step_id

    @property
    def name(self) -> str:
        return self.operation

    @property
    def description(self) -> str:
        return self.process_function

    @classmethod
    def from_mapping(cls, data: Any) -> "ProcessStep":
        if isinstance(data, ProcessStep):
            return data
        return cls(
            process_step_id=str(data.get("process_step_id", data.get("id", ""))),
            sequence=int(data.get("sequence", 0) or 0),
            operation=str(data.get("operation", data.get("name", ""))),
            process_function=str(
                data.get("process_function", data.get("description", ""))
            ),
            process_purpose=str(
                data.get(
                    "process_purpose",
                    data.get("purpose", data.get("operation_purpose", "")),
                )
            ),
            product_characteristics=_string_list(
                data.get("product_characteristics", data.get("product_characteristic_refs", []))
            ),
            process_characteristics=_string_list(
                data.get("process_characteristics", data.get("process_characteristic_refs", []))
            ),
            equipment=str(data.get("equipment", "")),
            tooling=str(data.get("tooling", data.get("fixture", ""))),
            gauges=_string_list(
                data.get("gauges", data.get("inspection_gauges", data.get("measurement_devices", [])))
            ),
            documents=_string_list(
                data.get("documents", data.get("document_refs", data.get("files", [])))
            ),
            flow_type=str(data.get("flow_type", data.get("process_type", ""))),
            owner=str(data.get("owner", "")),
            input_refs=_string_list(data.get("input_refs", [])),
            output_refs=_string_list(data.get("output_refs", [])),
            special_characteristics=_string_list(
                data.get("special_characteristics", [])
            ),
            evidence_refs=_string_list(data.get("evidence_refs", [])),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
        )


@dataclass
class Drawing:
    drawing_id: str = ""
    title: str = ""
    revision: str = ""
    source_ref: str = ""

    @classmethod
    def from_mapping(cls, data: Any) -> "Drawing":
        if isinstance(data, Drawing):
            return data
        if not isinstance(data, dict):
            return cls()
        return cls(
            drawing_id=str(data.get("drawing_id", data.get("id", ""))),
            title=str(data.get("title", data.get("name", ""))),
            revision=str(data.get("revision", "")),
            source_ref=str(data.get("source_ref", data.get("source", ""))),
        )


@dataclass
class Characteristic:
    characteristic_id: str = ""
    name: str = ""
    classification: str = ""
    specification: str = ""
    source_ref: str = ""

    @classmethod
    def from_mapping(cls, data: Any) -> "Characteristic":
        if isinstance(data, Characteristic):
            return data
        if not isinstance(data, dict):
            return cls()
        return cls(
            characteristic_id=str(data.get("characteristic_id", data.get("id", ""))),
            name=str(data.get("name", data.get("characteristic", ""))),
            classification=str(data.get("classification", "")),
            specification=str(data.get("specification", "")),
            source_ref=str(data.get("source_ref", data.get("source", ""))),
        )


@dataclass
class FailureModeCandidate:
    candidate_id: str = ""
    process_step_id: str = ""
    sequence: int = 0
    operation: str = ""
    process_function: str = ""
    failure_mode: str = ""
    source_rule: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    needs_confirmation: bool = False
    ai_inferred: bool = False
    source_process_step_id: str = ""
    characteristic_refs: list[str] = field(default_factory=list)
    created_by_stage: str = ""

    @classmethod
    def from_mapping(cls, data: Any) -> "FailureModeCandidate":
        if isinstance(data, FailureModeCandidate):
            return data
        if not isinstance(data, dict):
            return cls()
        return cls(
            candidate_id=str(data.get("candidate_id", data.get("id", ""))),
            process_step_id=str(data.get("process_step_id", data.get("step_no", ""))),
            sequence=int(data.get("sequence", 0) or 0),
            operation=str(data.get("operation", data.get("name", ""))),
            process_function=str(
                data.get("process_function", data.get("description", ""))
            ),
            failure_mode=str(data.get("failure_mode", "")),
            source_rule=str(data.get("source_rule", "")),
            evidence_refs=_string_list(data.get("evidence_refs", [])),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
            ai_inferred=bool(data.get("ai_inferred", False)),
            source_process_step_id=str(data.get("source_process_step_id", "")),
            characteristic_refs=_string_list(data.get("characteristic_refs", [])),
            created_by_stage=str(data.get("created_by_stage", "")),
        )


@dataclass
class FailureMode:
    pfmea_id: str
    process_step_id: str
    process_item: str = ""
    process_step: str = ""
    process_work_element: str = ""
    function_requirement: str = ""
    process_step_name: str = ""
    process_step_operation: str = ""
    process_function: str = ""
    product_characteristics: list[str] = field(default_factory=list)
    process_characteristics: list[str] = field(default_factory=list)
    failure_mode: str = ""
    failure_effect: str = ""
    severity: int = 0
    failure_cause: str = ""
    occurrence: int = 0
    prevention_control: str = ""
    detection_control: str = ""
    detection: int = 0
    action_priority: str = ""
    rpn: int = 0
    recommended_action: str = ""
    responsibility: str = ""
    target_date: str = ""
    action_status: str = ""
    actual_completion_date: str = ""
    after_severity: int = 0
    after_occurrence: int = 0
    after_detection: int = 0
    after_ap: str = ""
    after_rpn: int = 0
    remarks: str = ""
    classification: str = ""
    linked_control_plan_id: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    source_candidate_id: str = ""
    needs_confirmation: bool = False
    characteristic_refs: list[str] = field(default_factory=list)
    created_by_stage: str = ""

    @property
    def step_no(self) -> str:
        return self.process_step_id

    @property
    def process(self) -> str:
        return self.process_function

    @property
    def effect(self) -> str:
        return self.failure_effect

    @property
    def cause(self) -> str:
        return self.failure_cause

    @property
    def is_high_risk(self) -> bool:
        return self.action_priority.upper() == "H" or self.severity >= 9

    @property
    def is_mandatory_control(self) -> bool:
        return (
            self.is_high_risk
            or bool(self.classification.strip())
            or self.action_priority.upper() in {"H", "M"}
        )

    @classmethod
    def from_mapping(cls, data: Any) -> "FailureMode":
        if isinstance(data, FailureMode):
            return data
        return cls(
            pfmea_id=str(data.get("pfmea_id", data.get("id", ""))),
            process_step_id=str(data.get("process_step_id", data.get("step_no", ""))),
            process_item=str(data.get("process_item", "")),
            process_step=str(data.get("process_step", "")),
            process_work_element=str(data.get("process_work_element", "")),
            function_requirement=str(
                data.get("function_requirement", data.get("requirement", ""))
            ),
            process_step_name=str(data.get("process_step_name", data.get("operation", ""))),
            process_step_operation=str(
                data.get("process_step_operation", data.get("operation", ""))
            ),
            process_function=str(data.get("process_function", data.get("process", ""))),
            product_characteristics=_string_list(
                data.get("product_characteristics", [])
            ),
            process_characteristics=_string_list(
                data.get("process_characteristics", [])
            ),
            failure_mode=str(data.get("failure_mode", "")),
            failure_effect=str(data.get("failure_effect", data.get("effect", ""))),
            severity=int(data.get("severity", 0) or 0),
            failure_cause=str(data.get("failure_cause", data.get("cause", ""))),
            occurrence=int(data.get("occurrence", 0) or 0),
            prevention_control=str(data.get("prevention_control", "")),
            detection_control=str(data.get("detection_control", "")),
            detection=int(data.get("detection", 0) or 0),
            action_priority=str(data.get("action_priority", "")),
            rpn=int(data.get("rpn", 0) or 0),
            recommended_action=str(data.get("recommended_action", "")),
            responsibility=str(data.get("responsibility", data.get("owner", ""))),
            target_date=str(data.get("target_date", "")),
            action_status=str(data.get("action_status", data.get("status", ""))),
            actual_completion_date=str(
                data.get("actual_completion_date", data.get("completion_date", ""))
            ),
            after_severity=int(data.get("after_severity", 0) or 0),
            after_occurrence=int(data.get("after_occurrence", 0) or 0),
            after_detection=int(data.get("after_detection", 0) or 0),
            after_ap=str(data.get("after_ap", "")),
            after_rpn=int(data.get("after_rpn", 0) or 0),
            remarks=str(data.get("remarks", data.get("note", ""))),
            classification=str(data.get("classification", "")),
            linked_control_plan_id=str(data.get("linked_control_plan_id", "")),
            evidence_refs=_string_list(data.get("evidence_refs", [])),
            source_candidate_id=str(data.get("source_candidate_id", "")),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
            characteristic_refs=_string_list(data.get("characteristic_refs", [])),
            created_by_stage=str(data.get("created_by_stage", "")),
        )


@dataclass
class ControlItem:
    control_plan_id: str
    process_step_id: str
    pfmea_id: str = ""
    product_process_characteristic: str = ""
    specification: str = ""
    classification: str = ""
    measurement_method: str = ""
    sample_size: str = ""
    sample_frequency: str = ""
    control_method: str = ""
    reaction_plan: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    needs_confirmation: bool = False
    characteristic_refs: list[str] = field(default_factory=list)
    source_pfmea_id: str = ""
    source_failure_cause: str = ""
    source_prevention_control: str = ""
    source_detection_control: str = ""
    source_special_characteristics: list[str] = field(default_factory=list)
    source_high_risk: bool = False
    created_by_stage: str = ""

    @property
    def step_no(self) -> str:
        return self.process_step_id

    @property
    def characteristic(self) -> str:
        return self.product_process_characteristic

    @property
    def measurement(self) -> str:
        return self.measurement_method

    @classmethod
    def from_mapping(cls, data: Any) -> "ControlItem":
        if isinstance(data, ControlItem):
            return data
        return cls(
            control_plan_id=str(data.get("control_plan_id", data.get("id", ""))),
            process_step_id=str(data.get("process_step_id", data.get("step_no", ""))),
            pfmea_id=str(data.get("pfmea_id", "")),
            product_process_characteristic=str(
                data.get(
                    "product_process_characteristic", data.get("characteristic", "")
                )
            ),
            specification=str(data.get("specification", "")),
            classification=str(data.get("classification", "")),
            measurement_method=str(
                data.get("measurement_method", data.get("measurement", ""))
            ),
            sample_size=str(data.get("sample_size", "")),
            sample_frequency=str(data.get("sample_frequency", "")),
            control_method=str(data.get("control_method", "")),
            reaction_plan=str(data.get("reaction_plan", "")),
            evidence_refs=_string_list(data.get("evidence_refs", [])),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
            characteristic_refs=_string_list(data.get("characteristic_refs", [])),
            source_pfmea_id=str(data.get("source_pfmea_id", "")),
            source_failure_cause=str(data.get("source_failure_cause", "")),
            source_prevention_control=str(data.get("source_prevention_control", "")),
            source_detection_control=str(data.get("source_detection_control", "")),
            source_special_characteristics=_string_list(
                data.get("source_special_characteristics", [])
            ),
            source_high_risk=bool(data.get("source_high_risk", False)),
            created_by_stage=str(data.get("created_by_stage", "")),
        )


@dataclass
class Evidence:
    evidence_id: str = ""
    source: str = ""
    content: str = ""
    confidence: float | None = None
    ai_inferred: bool = False
    needs_confirmation: bool = False

    @classmethod
    def from_mapping(cls, data: Any) -> "Evidence":
        if isinstance(data, Evidence):
            return data
        if not isinstance(data, dict):
            return cls()
        raw_confidence = data.get("confidence")
        try:
            confidence = None if raw_confidence in {None, ""} else float(raw_confidence)
        except (TypeError, ValueError):
            confidence = None
        return cls(
            evidence_id=str(data.get("evidence_id", data.get("id", ""))),
            source=str(data.get("source", "")),
            content=str(data.get("content", data.get("text", ""))),
            confidence=confidence,
            ai_inferred=bool(data.get("ai_inferred", False)),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
        )


@dataclass
class TraceLink:
    from_id: str
    to_id: str
    link_type: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    trace_link_id: str = ""
    from_type: str = ""
    to_type: str = ""
    created_by_stage: str = ""
    confidence: float | None = None
    ai_inferred: bool = False
    needs_confirmation: bool = False

    @classmethod
    def from_mapping(cls, data: Any) -> "TraceLink":
        if isinstance(data, TraceLink):
            return data
        raw_confidence = data.get("confidence")
        try:
            confidence = None if raw_confidence in {None, ""} else float(raw_confidence)
        except (TypeError, ValueError):
            confidence = None
        return cls(
            from_id=str(data.get("from", data.get("from_id", ""))),
            to_id=str(data.get("to", data.get("to_id", ""))),
            link_type=str(data.get("link_type", "")),
            evidence_refs=_string_list(data.get("evidence_refs", [])),
            trace_link_id=str(data.get("trace_link_id", data.get("id", ""))),
            from_type=str(data.get("from_type", "")),
            to_type=str(data.get("to_type", "")),
            created_by_stage=str(data.get("created_by_stage", "")),
            confidence=confidence,
            ai_inferred=bool(data.get("ai_inferred", False)),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
        )


@dataclass
class APQPChain:
    product: Product = field(default_factory=Product)
    drawings: list[Drawing] = field(default_factory=list)
    characteristics: list[Characteristic] = field(default_factory=list)
    process_steps: list[ProcessStep] = field(default_factory=list)
    failure_mode_candidates: list[FailureModeCandidate] = field(default_factory=list)
    failure_modes: list[FailureMode] = field(default_factory=list)
    controls: list[ControlItem] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    links: list[TraceLink] = field(default_factory=list)
    pending_fields: list[Any] = field(default_factory=list)
    ai_inferred_items: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = ""
    document_type: str = "apqp_chain"

    def __init__(self, **payload: Any) -> None:
        normalized = normalize_fixture_payload(payload)
        self.product = Product.from_mapping(normalized.get("product", {}))
        self.drawings = [
            Drawing.from_mapping(item) for item in normalized.get("drawings", [])
        ]
        self.characteristics = [
            Characteristic.from_mapping(item)
            for item in normalized.get("characteristics", [])
        ]
        self.process_steps = [
            ProcessStep.from_mapping(item)
            for item in normalized.get("process_steps", [])
        ]
        self.failure_mode_candidates = [
            FailureModeCandidate.from_mapping(item)
            for item in normalized.get("failure_mode_candidates", [])
        ]
        self.failure_modes = [
            FailureMode.from_mapping(item)
            for item in normalized.get("failure_modes", [])
        ]
        self.controls = [
            ControlItem.from_mapping(item) for item in normalized.get("controls", [])
        ]
        self.evidence = [
            Evidence.from_mapping(item) for item in normalized.get("evidence", [])
        ]
        self.links = [
            TraceLink.from_mapping(item) for item in normalized.get("links", [])
        ]
        self.pending_fields = list(normalized.get("pending_fields", []))
        self.ai_inferred_items = list(normalized.get("ai_inferred_items", []))
        self.metadata = dict(normalized.get("metadata", {}))
        self.schema_version = str(normalized.get("schema_version", ""))
        self.document_type = str(normalized.get("document_type", "apqp_chain"))

    @property
    def slug(self) -> str:
        return self.product.sample_id or self.product.part_number or "apqp_chain"

    @property
    def display_name(self) -> str:
        return self.product.part_name

    @property
    def part_number(self) -> str:
        return self.product.part_number

    @property
    def stage(self) -> str:
        return self.product.phase

    @property
    def steps(self) -> list[ProcessStep]:
        return self.process_steps

    @property
    def pfmea_items(self) -> list[FailureMode]:
        return self.failure_modes

    @property
    def control_plan_items(self) -> list[ControlItem]:
        return self.controls

    @property
    def critical_characteristics(self) -> list[str]:
        values = [step.special_characteristics for step in self.process_steps]
        values.extend(
            [
                [item.classification]
                for item in self.failure_modes
                if item.classification
            ]
        )
        return sorted({value for group in values for value in group if value})

    @property
    def traceability_matrix(self) -> list[dict[str, str]]:
        controls_by_pfmea = {
            item.pfmea_id: item.control_plan_id
            for item in self.controls
            if item.pfmea_id
        }
        step_ids = {step.process_step_id: step for step in self.process_steps}
        rows: list[dict[str, str]] = []
        for failure in self.failure_modes:
            step = step_ids.get(failure.process_step_id)
            rows.append(
                {
                    "step_no": failure.process_step_id,
                    "characteristic": failure.classification,
                    "process_flow_ref": step.process_step_id if step else "",
                    "pfmea_ref": failure.pfmea_id,
                    "control_plan_ref": controls_by_pfmea.get(
                        failure.pfmea_id, failure.linked_control_plan_id
                    ),
                }
            )
        return rows

    @classmethod
    def model_validate(cls, payload: dict[str, Any]) -> "APQPChain":
        return cls(**payload)

    @classmethod
    def parse_obj(cls, payload: dict[str, Any]) -> "APQPChain":
        return cls(**payload)

    def model_dump(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "schema_version": self.schema_version,
            "product": self.product.__dict__,
            "drawings": [item.__dict__ for item in self.drawings],
            "characteristics": [item.__dict__ for item in self.characteristics],
            "process_steps": [item.__dict__ for item in self.process_steps],
            "failure_mode_candidates": [
                item.__dict__ for item in self.failure_mode_candidates
            ],
            "failure_modes": [item.__dict__ for item in self.failure_modes],
            "controls": [item.__dict__ for item in self.controls],
            "evidence": [item.__dict__ for item in self.evidence],
            "links": [item.__dict__ for item in self.links],
            "pending_fields": self.pending_fields,
            "ai_inferred_items": self.ai_inferred_items,
            "metadata": self.metadata,
        }


def normalize_fixture_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "process_flow" in payload or "pfmea" in payload or "control_plan" in payload:
        return _normalize_combined_payload(payload)

    document_type = str(payload.get("document_type", ""))
    normalized = {
        "document_type": document_type or payload.get("document_type", "apqp_chain"),
        "schema_version": payload.get("schema_version", ""),
        "product": payload.get("product", {}),
        "drawings": payload.get("drawings", []),
        "characteristics": payload.get("characteristics", []),
        "process_steps": payload.get("process_steps", payload.get("steps", [])),
        "failure_mode_candidates": payload.get(
            "failure_mode_candidates", payload.get("candidates", [])
        ),
        "failure_modes": payload.get("failure_modes", payload.get("pfmea_items", [])),
        "controls": payload.get("controls", payload.get("control_plan_items", [])),
        "evidence": payload.get("evidence", []),
        "links": payload.get("links", []),
        "pending_fields": payload.get("pending_fields", []),
        "ai_inferred_items": payload.get("ai_inferred_items", []),
        "metadata": payload.get("metadata", {}),
    }
    if document_type == "process_flow":
        normalized["process_steps"] = payload.get("steps", [])
    elif document_type == "pfmea":
        normalized["failure_modes"] = payload.get("rows", [])
    elif document_type == "control_plan":
        normalized["controls"] = payload.get("rows", [])
    return normalized


def _normalize_combined_payload(payload: dict[str, Any]) -> dict[str, Any]:
    process_flow = payload.get("process_flow") or {}
    pfmea = payload.get("pfmea") or {}
    control_plan = payload.get("control_plan") or {}
    product = (
        payload.get("product")
        or process_flow.get("product")
        or pfmea.get("product")
        or control_plan.get("product")
        or {}
    )
    return {
        "document_type": "apqp_chain",
        "schema_version": payload.get("schema_version")
        or process_flow.get("schema_version")
        or pfmea.get("schema_version")
        or control_plan.get("schema_version", ""),
        "product": product,
        "drawings": payload.get("drawings", []),
        "characteristics": payload.get("characteristics", []),
        "process_steps": payload.get("process_steps", process_flow.get("steps", [])),
        "failure_mode_candidates": payload.get(
            "failure_mode_candidates",
            _first_list(
                payload.get("candidates"),
                payload.get("failure_mode_candidates"),
                (payload.get("failure_mode_candidates_bundle") or {}).get("candidates"),
                (payload.get("failure_mode_candidates_bundle") or {}).get(
                    "failure_mode_candidates"
                ),
            ),
        ),
        "failure_modes": payload.get("failure_modes", pfmea.get("rows", [])),
        "controls": payload.get("controls", control_plan.get("rows", [])),
        "evidence": payload.get("evidence", []),
        "links": payload.get("links", process_flow.get("links", [])),
        "pending_fields": payload.get("pending_fields", []),
        "ai_inferred_items": payload.get("ai_inferred_items", []),
        "metadata": payload.get("metadata", {}),
    }


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return value
    return []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def load_apqp_chain(fixture: Any) -> dict[str, Any]:
    """Compatibility wrapper for the fixture JSON adapter.

    New code should use ``minos_core.adapters.fixture_json`` or pipeline entry
    points. The wrapper remains so older callers do not have to import adapters
    directly yet.
    """

    from .adapters.fixture_json import load_fixture_payload

    return load_fixture_payload(fixture)


def load_chain(fixture: Any) -> dict[str, Any]:
    return load_apqp_chain(fixture)


def load_domain_bundle(fixture: Any) -> dict[str, Any]:
    return load_apqp_chain(fixture)
