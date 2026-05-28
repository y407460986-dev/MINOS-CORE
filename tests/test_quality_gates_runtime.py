"""Runtime error tests for quality gates module.

Tests that verify critical runtime bugs are fixed:
- Logger import availability
- Validation logic correctness
"""

import pytest
from minos_core.quality_gates import evaluate_stage_gate
from minos_core.domain import APQPChain


def test_logger_available_when_linkage_fails(monkeypatch):
    """Logger should be defined when three_table_linkage evaluation fails.

    Regression test for line 280 NameError.
    """
    # Mock evaluate_three_table_linkage to raise exception
    def mock_linkage(*args, **kwargs):
        raise RuntimeError("Linkage evaluation failed")

    monkeypatch.setattr(
        "minos_core.quality_gates.evaluate_three_table_linkage",
        mock_linkage
    )

    chain = APQPChain(metadata={"strict_aiag_vda_pfmea_gate": True})

    # Should not raise NameError: name 'logger' is not defined
    gate = evaluate_stage_gate(chain, stage="validate")
    assert gate is not None


def test_validation_check_uses_ok_attribute():
    """Validation check should use .ok attribute, not truthiness of object.

    Regression test for line 172 inverted logic.
    """
    from minos_core.quality_gates import _export_gate_failure_message, StageQualityGate
    from minos_core.validation import ChainValidationResult
    from minos_core.domain import APQPChain
    from minos_core.audit import AuditReport

    # Create a gate with failed validation
    chain = APQPChain()
    validation = ChainValidationResult(
        ok=False,
        messages=["Test validation error"],
        chain=chain
    )
    audit = AuditReport(counts={})

    gate = StageQualityGate(
        stage="export",
        can_continue=False,
        allow_user_export=False,
        evidence_sufficient=False,
        validation=validation,
        audit=audit
    )

    # Should generate failure message when validation.ok is False
    message = _export_gate_failure_message(gate)
    assert "APQP chain validation failed:" in message
    assert "Test validation error" in message
