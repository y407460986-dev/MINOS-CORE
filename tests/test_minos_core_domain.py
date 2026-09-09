"""Tests for minos_core.domain module."""


import pytest

from minos_core.domain import (
    APQPChain,
    Evidence,
    FailureMode,
    ProcessStep,
    Product,
    TraceLink,
)


class TestFailureModeValidation:
    """Test FailureMode.__post_init__() validation logic."""

    def test_valid_severity_values(self):
        """Test that severity values 1-10 are accepted."""
        for severity in range(1, 11):
            fm = FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                severity=severity
            )
            assert fm.severity == severity

    def test_severity_zero_is_valid(self):
        """Test that severity=0 is valid (means not set)."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            severity=0
        )
        assert fm.severity == 0

    def test_severity_below_range_raises_value_error(self):
        """Test that severity < 1 (except 0) raises ValueError."""
        with pytest.raises(ValueError, match="severity must be 1-10, got -1"):
            FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                severity=-1
            )

    def test_severity_above_range_raises_value_error(self):
        """Test that severity > 10 raises ValueError."""
        with pytest.raises(ValueError, match="severity must be 1-10, got 11"):
            FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                severity=11
            )

    def test_valid_occurrence_values(self):
        """Test that occurrence values 1-10 are accepted."""
        for occurrence in range(1, 11):
            fm = FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                occurrence=occurrence
            )
            assert fm.occurrence == occurrence

    def test_occurrence_zero_is_valid(self):
        """Test that occurrence=0 is valid (means not set)."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            occurrence=0
        )
        assert fm.occurrence == 0

    def test_occurrence_below_range_raises_value_error(self):
        """Test that occurrence < 1 (except 0) raises ValueError."""
        with pytest.raises(ValueError, match="occurrence must be 1-10, got -1"):
            FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                occurrence=-1
            )

    def test_occurrence_above_range_raises_value_error(self):
        """Test that occurrence > 10 raises ValueError."""
        with pytest.raises(ValueError, match="occurrence must be 1-10, got 15"):
            FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                occurrence=15
            )

    def test_valid_detection_values(self):
        """Test that detection values 1-10 are accepted."""
        for detection in range(1, 11):
            fm = FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                detection=detection
            )
            assert fm.detection == detection

    def test_detection_zero_is_valid(self):
        """Test that detection=0 is valid (means not set)."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            detection=0
        )
        assert fm.detection == 0

    def test_detection_below_range_raises_value_error(self):
        """Test that detection < 1 (except 0) raises ValueError."""
        with pytest.raises(ValueError, match="detection must be 1-10, got -5"):
            FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                detection=-5
            )

    def test_detection_above_range_raises_value_error(self):
        """Test that detection > 10 raises ValueError."""
        with pytest.raises(ValueError, match="detection must be 1-10, got 12"):
            FailureMode(
                pfmea_id="FM001",
                process_step_id="STEP001",
                detection=12
            )


class TestFailureModeFromMapping:
    """Test FailureMode.from_mapping() with aliases."""

    def test_from_mapping_with_standard_fields(self):
        """Test from_mapping with standard field names."""
        data = {
            "pfmea_id": "FM001",
            "process_step_id": "STEP001",
            "failure_mode": "Crack",
            "failure_effect": "Leakage",
            "severity": 8,
            "failure_cause": "Excessive stress",
            "occurrence": 5,
            "detection": 3
        }

        fm = FailureMode.from_mapping(data)

        assert fm.pfmea_id == "FM001"
        assert fm.process_step_id == "STEP001"
        assert fm.failure_mode == "Crack"
        assert fm.failure_effect == "Leakage"
        assert fm.severity == 8
        assert fm.failure_cause == "Excessive stress"
        assert fm.occurrence == 5
        assert fm.detection == 3

    def test_from_mapping_with_id_alias(self):
        """Test from_mapping with 'id' alias for pfmea_id."""
        data = {
            "id": "FM002",
            "process_step_id": "STEP001"
        }

        fm = FailureMode.from_mapping(data)

        assert fm.pfmea_id == "FM002"

    def test_from_mapping_with_step_no_alias(self):
        """Test from_mapping with 'step_no' alias for process_step_id."""
        data = {
            "pfmea_id": "FM001",
            "step_no": "STEP002"
        }

        fm = FailureMode.from_mapping(data)

        assert fm.process_step_id == "STEP002"

    def test_from_mapping_with_effect_alias(self):
        """Test from_mapping with 'effect' alias for failure_effect."""
        data = {
            "pfmea_id": "FM001",
            "process_step_id": "STEP001",
            "effect": "Product defect"
        }

        fm = FailureMode.from_mapping(data)

        assert fm.failure_effect == "Product defect"

    def test_from_mapping_with_cause_alias(self):
        """Test from_mapping with 'cause' alias for failure_cause."""
        data = {
            "pfmea_id": "FM001",
            "process_step_id": "STEP001",
            "cause": "Operator error"
        }

        fm = FailureMode.from_mapping(data)

        assert fm.failure_cause == "Operator error"

    def test_from_mapping_with_process_alias(self):
        """Test from_mapping with 'process' alias for process_function."""
        data = {
            "pfmea_id": "FM001",
            "process_step_id": "STEP001",
            "process": "Welding"
        }

        fm = FailureMode.from_mapping(data)

        assert fm.process_function == "Welding"

    def test_from_mapping_type_coercion_string_to_int(self):
        """Test that string numbers are coerced to int."""
        data = {
            "pfmea_id": "FM001",
            "process_step_id": "STEP001",
            "severity": "7",
            "occurrence": "4",
            "detection": "2"
        }

        fm = FailureMode.from_mapping(data)

        assert fm.severity == 7
        assert fm.occurrence == 4
        assert fm.detection == 2

    def test_from_mapping_type_coercion_none_to_zero(self):
        """Test that None values are coerced to 0 for int fields."""
        data = {
            "pfmea_id": "FM001",
            "process_step_id": "STEP001",
            "severity": None,
            "occurrence": None,
            "detection": None
        }

        fm = FailureMode.from_mapping(data)

        assert fm.severity == 0
        assert fm.occurrence == 0
        assert fm.detection == 0

    def test_from_mapping_type_coercion_empty_string_to_zero(self):
        """Test that empty strings are coerced to 0 for int fields."""
        data = {
            "pfmea_id": "FM001",
            "process_step_id": "STEP001",
            "severity": "",
            "occurrence": "",
            "detection": ""
        }

        fm = FailureMode.from_mapping(data)

        assert fm.severity == 0
        assert fm.occurrence == 0
        assert fm.detection == 0

    def test_from_mapping_already_failure_mode_returns_same(self):
        """Test that passing a FailureMode returns it unchanged."""
        original = FailureMode(pfmea_id="FM001", process_step_id="STEP001")

        result = FailureMode.from_mapping(original)

        assert result is original

    def test_from_mapping_invalid_type_raises_type_error(self):
        """Test that passing non-mapping raises TypeError."""
        with pytest.raises(TypeError, match="FailureMode.from_mapping expected a mapping"):
            FailureMode.from_mapping("not a mapping")

    def test_from_mapping_with_lists(self):
        """Test from_mapping with list fields."""
        data = {
            "pfmea_id": "FM001",
            "process_step_id": "STEP001",
            "product_characteristics": ["Dimension A", "Dimension B"],
            "process_characteristics": ["Temperature", "Pressure"],
            "evidence_refs": ["EV001", "EV002"]
        }

        fm = FailureMode.from_mapping(data)

        assert fm.product_characteristics == ["Dimension A", "Dimension B"]
        assert fm.process_characteristics == ["Temperature", "Pressure"]
        assert fm.evidence_refs == ["EV001", "EV002"]


class TestFailureModeProperties:
    """Test FailureMode computed properties."""

    def test_is_high_risk_severity_9(self):
        """Test is_high_risk returns True when severity >= 9."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            severity=9
        )

        assert fm.is_high_risk is True

    def test_is_high_risk_severity_10(self):
        """Test is_high_risk returns True when severity = 10."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            severity=10
        )

        assert fm.is_high_risk is True

    def test_is_high_risk_action_priority_h(self):
        """Test is_high_risk returns True when action_priority = 'H'."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            severity=5,
            action_priority="H"
        )

        assert fm.is_high_risk is True

    def test_is_high_risk_action_priority_lowercase_h(self):
        """Test is_high_risk returns True when action_priority = 'h' (case insensitive)."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            severity=5,
            action_priority="h"
        )

        assert fm.is_high_risk is True

    def test_is_high_risk_false(self):
        """Test is_high_risk returns False when neither condition is met."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            severity=5,
            action_priority="M"
        )

        assert fm.is_high_risk is False

    def test_step_no_property(self):
        """Test step_no property returns process_step_id."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP123"
        )

        assert fm.step_no == "STEP123"

    def test_process_property(self):
        """Test process property returns process_function."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            process_function="Assembly"
        )

        assert fm.process == "Assembly"

    def test_effect_property(self):
        """Test effect property returns failure_effect."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            failure_effect="Customer complaint"
        )

        assert fm.effect == "Customer complaint"

    def test_cause_property(self):
        """Test cause property returns failure_cause."""
        fm = FailureMode(
            pfmea_id="FM001",
            process_step_id="STEP001",
            failure_cause="Material defect"
        )

        assert fm.cause == "Material defect"


class TestProductFromMapping:
    """Test Product.from_mapping() with aliases."""

    def test_from_mapping_with_standard_fields(self):
        """Test from_mapping with standard field names."""
        data = {
            "sample_id": "S001",
            "part_number": "PN12345",
            "part_name": "Bracket",
            "revision": "A",
            "phase": "PPAP"
        }

        product = Product.from_mapping(data)

        assert product.sample_id == "S001"
        assert product.part_number == "PN12345"
        assert product.part_name == "Bracket"
        assert product.revision == "A"
        assert product.phase == "PPAP"

    def test_from_mapping_with_missing_fields(self):
        """Test from_mapping with missing fields defaults to empty strings."""
        data = {}

        product = Product.from_mapping(data)

        assert product.sample_id == ""
        assert product.part_number == ""
        assert product.part_name == ""
        assert product.revision == ""
        assert product.phase == ""

    def test_from_mapping_already_product_returns_same(self):
        """Test that passing a Product returns it unchanged."""
        original = Product(sample_id="S001", part_number="PN001")

        result = Product.from_mapping(original)

        assert result is original


class TestProcessStepFromMapping:
    """Test ProcessStep.from_mapping() with aliases."""

    def test_from_mapping_with_id_alias(self):
        """Test from_mapping with 'id' alias for process_step_id."""
        data = {
            "id": "STEP001",
            "operation": "Welding"
        }

        step = ProcessStep.from_mapping(data)

        assert step.process_step_id == "STEP001"

    def test_from_mapping_with_name_alias(self):
        """Test from_mapping with 'name' alias for operation."""
        data = {
            "process_step_id": "STEP001",
            "name": "Assembly"
        }

        step = ProcessStep.from_mapping(data)

        assert step.operation == "Assembly"

    def test_from_mapping_with_description_alias(self):
        """Test from_mapping with 'description' alias for process_function."""
        data = {
            "process_step_id": "STEP001",
            "description": "Join parts together"
        }

        step = ProcessStep.from_mapping(data)

        assert step.process_function == "Join parts together"

    def test_from_mapping_with_fixture_alias(self):
        """Test from_mapping with 'fixture' alias for tooling."""
        data = {
            "process_step_id": "STEP001",
            "fixture": "Jig A"
        }

        step = ProcessStep.from_mapping(data)

        assert step.tooling == "Jig A"


class TestAPQPChainConstruction:
    """Test APQPChain construction and validation."""

    def test_apqp_chain_basic_construction(self):
        """Test basic APQPChain construction."""
        payload = {
            "product": {
                "sample_id": "S001",
                "part_number": "PN001",
                "part_name": "Test Part"
            },
            "process_steps": [],
            "failure_modes": [],
            "controls": []
        }

        chain = APQPChain(**payload)

        assert chain.product.sample_id == "S001"
        assert chain.product.part_number == "PN001"
        assert chain.process_steps == []
        assert chain.failure_modes == []
        assert chain.controls == []

    def test_apqp_chain_missing_product_uses_default(self):
        """Test that missing 'product' field uses default empty Product."""
        payload = {
            "process_steps": []
        }

        chain = APQPChain(**payload)

        # normalize_fixture_payload provides default empty dict for product
        assert chain.product.sample_id == ""
        assert chain.product.part_number == ""

    def test_apqp_chain_requires_kwargs(self):
        """Test that APQPChain requires keyword arguments."""
        with pytest.raises(TypeError):
            APQPChain({"product": {"sample_id": "S001"}})

    def test_apqp_chain_with_process_steps(self):
        """Test APQPChain with process steps."""
        payload = {
            "product": {"sample_id": "S001"},
            "process_steps": [
                {"process_step_id": "STEP001", "operation": "Welding"},
                {"process_step_id": "STEP002", "operation": "Inspection"}
            ]
        }

        chain = APQPChain(**payload)

        assert len(chain.process_steps) == 2
        assert chain.process_steps[0].process_step_id == "STEP001"
        assert chain.process_steps[1].operation == "Inspection"

    def test_apqp_chain_with_failure_modes(self):
        """Test APQPChain with failure modes."""
        payload = {
            "product": {"sample_id": "S001"},
            "failure_modes": [
                {"pfmea_id": "FM001", "process_step_id": "STEP001", "severity": 7}
            ]
        }

        chain = APQPChain(**payload)

        assert len(chain.failure_modes) == 1
        assert chain.failure_modes[0].pfmea_id == "FM001"
        assert chain.failure_modes[0].severity == 7

    def test_apqp_chain_slug_property(self):
        """Test APQPChain slug property."""
        payload = {
            "product": {"sample_id": "S001", "part_number": "PN001"}
        }

        chain = APQPChain(**payload)

        assert chain.slug == "S001"

    def test_apqp_chain_slug_fallback_to_part_number(self):
        """Test APQPChain slug falls back to part_number."""
        payload = {
            "product": {"sample_id": "", "part_number": "PN001"}
        }

        chain = APQPChain(**payload)

        assert chain.slug == "PN001"

    def test_apqp_chain_display_name_property(self):
        """Test APQPChain display_name property."""
        payload = {
            "product": {"part_name": "Test Bracket"}
        }

        chain = APQPChain(**payload)

        assert chain.display_name == "Test Bracket"


class TestEvidenceFromMapping:
    """Test Evidence.from_mapping() with confidence handling."""

    def test_from_mapping_with_valid_confidence(self):
        """Test from_mapping with valid confidence value."""
        data = {
            "evidence_id": "EV001",
            "source": "Drawing",
            "content": "Dimension spec",
            "confidence": 0.95
        }

        evidence = Evidence.from_mapping(data)

        assert evidence.confidence == 0.95

    def test_from_mapping_with_string_confidence(self):
        """Test from_mapping with string confidence value."""
        data = {
            "evidence_id": "EV001",
            "confidence": "0.85"
        }

        evidence = Evidence.from_mapping(data)

        assert evidence.confidence == 0.85

    def test_from_mapping_with_none_confidence(self):
        """Test from_mapping with None confidence."""
        data = {
            "evidence_id": "EV001",
            "confidence": None
        }

        evidence = Evidence.from_mapping(data)

        assert evidence.confidence is None

    def test_from_mapping_with_empty_string_confidence(self):
        """Test from_mapping with empty string confidence."""
        data = {
            "evidence_id": "EV001",
            "confidence": ""
        }

        evidence = Evidence.from_mapping(data)

        assert evidence.confidence is None

    def test_from_mapping_with_invalid_confidence(self):
        """Test from_mapping with invalid confidence value."""
        data = {
            "evidence_id": "EV001",
            "confidence": "invalid"
        }

        evidence = Evidence.from_mapping(data)

        assert evidence.confidence is None


class TestTraceLinkFromMapping:
    """Test TraceLink.from_mapping() with aliases."""

    def test_from_mapping_with_from_alias(self):
        """Test from_mapping with 'from' alias for from_id."""
        data = {
            "from": "STEP001",
            "to": "FM001",
            "link_type": "step_to_failure"
        }

        link = TraceLink.from_mapping(data)

        assert link.from_id == "STEP001"
        assert link.to_id == "FM001"

    def test_from_mapping_with_to_alias(self):
        """Test from_mapping with 'to' alias for to_id."""
        data = {
            "from_id": "STEP001",
            "to": "FM001"
        }

        link = TraceLink.from_mapping(data)

        assert link.to_id == "FM001"
