from __future__ import annotations

import copy

from minos_core.adapters.fixture_json import load_fixture_payload


ROOT_FIXTURE = "D:/MINOS-CORE/tests/fixtures/apqp_chain"
NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _fixture() -> dict:
    return load_fixture_payload(ROOT_FIXTURE)


def _three_table_result() -> dict:
    payload = _fixture()
    return {
        "document_type": "three_table_generation_result",
        "schema_version": "minos-core.three_table_generation_result.v1",
        "status": "needs_review",
        "status_display": "待人工复核",
        "blocked_stage": None,
        "drawing_analysis": {"evidence": copy.deepcopy(payload["evidence"])},
        "process_flow": copy.deepcopy(payload["process_flow"]),
        "pfmea": copy.deepcopy(payload["pfmea"]),
        "control_plan": copy.deepcopy(payload["control_plan"]),
        "chain": {
            "document_type": "apqp_chain",
            "schema_version": "minos-core.generated.v1",
            "product": copy.deepcopy(payload["process_flow"]["product"]),
            "process_steps": copy.deepcopy(payload["process_flow"]["steps"]),
            "failure_modes": copy.deepcopy(payload["pfmea"]["rows"]),
            "controls": copy.deepcopy(payload["control_plan"]["rows"]),
            "evidence": copy.deepcopy(payload["evidence"]),
            "links": copy.deepcopy(payload["process_flow"]["links"]),
            "metadata": {},
        },
        "quality_gate": {},
        "quality_gates": {},
        "exports": {},
        "manifest": {},
        "manual_review": {"required": True, "items": []},
        "warnings": [],
    }


