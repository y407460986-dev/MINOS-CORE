"""Tests for quality_gates.config_loader module.

Covers:
- load_quality_gate_config: loading from default path, file path, and missing files
- validate_config: structural and range validation rules
- get_default_config: guaranteed valid defaults
- get_pfd_config / get_pfmea_config / etc.: section extraction
"""

import tempfile
import unittest
from pathlib import Path

import yaml

from minos_core.quality_gates.config_loader import (
    get_default_config,
    get_default_config_path,
    get_pfd_config,
    get_pfmea_config,
    load_quality_gate_config,
    validate_config,
)


class LoadQualityGateConfigTest(unittest.TestCase):
    """Tests for load_quality_gate_config()."""

    def test_load_default_config_returns_dict_with_required_sections(self):
        """Loading with path=None should return a config dict containing all gate sections."""
        config = load_quality_gate_config()

        self.assertIsInstance(config, dict)
        self.assertIn("pfd_gate", config)
        self.assertIn("pfmea_gate", config)
        self.assertIn("control_plan_gate", config)
        self.assertIn("export_gate", config)

    def test_load_from_temp_yaml_returns_correct_gate_definitions(self):
        """Loading from a temporary YAML file should return its contents faithfully."""
        test_config = {
            "pfd_gate": {"min_process_steps": 5, "evidence_coverage_threshold": 0.9},
            "pfmea_gate": {"min_failure_modes": 2, "severity_range": [1, 5]},
            "control_plan_gate": {"min_control_items": 3},
            "export_gate": {"require_all_gates_pass": False},
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(test_config, f)
            tmp_path = f.name

        try:
            config = load_quality_gate_config(tmp_path)

            self.assertEqual(config["pfd_gate"]["min_process_steps"], 5)
            self.assertEqual(
                config["pfd_gate"]["evidence_coverage_threshold"], 0.9
            )
            self.assertEqual(config["pfmea_gate"]["min_failure_modes"], 2)
            self.assertEqual(config["pfmea_gate"]["severity_range"], [1, 5])
            self.assertEqual(config["control_plan_gate"]["min_control_items"], 3)
            self.assertFalse(config["export_gate"]["require_all_gates_pass"])
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_load_from_missing_path_returns_default_config(self):
        """Loading from a path that does not exist should return the built-in default config."""
        missing = Path(tempfile.gettempdir()) / "_nonexistent_quality_gates_file_.yaml"
        if missing.exists():
            missing.unlink()

        config = load_quality_gate_config(str(missing))

        expected = get_default_config()
        self.assertEqual(config, expected)

    def test_invalid_yaml_raises_value_error(self):
        """Loading a file with malformed YAML should raise ValueError."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("{bad: yaml: unquoted: colons: }")
            tmp_path = f.name

        try:
            with self.assertRaises(ValueError):
                load_quality_gate_config(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_get_default_config_path_returns_pathlib_path(self):
        """get_default_config_path should return a Path object."""
        path = get_default_config_path()
        self.assertIsInstance(path, Path)


class ValidateConfigTest(unittest.TestCase):
    """Tests for validate_config()."""

    def test_valid_default_config_returns_empty_errors(self):
        """The built-in default config should pass validation with zero errors."""
        config = get_default_config()
        errors = validate_config(config)
        self.assertEqual(errors, [])

    def test_valid_custom_config_returns_empty_errors(self):
        """A well-formed custom config should pass validation."""
        config = {
            "pfd_gate": {
                "min_process_steps": 4,
                "evidence_coverage_threshold": 0.8,
            },
            "pfmea_gate": {
                "severity_range": [1, 10],
            },
            "control_plan_gate": {},
        }
        errors = validate_config(config)
        self.assertEqual(errors, [])

    def test_missing_pfd_gate_returns_error(self):
        """Omitting 'pfd_gate' should produce a validation error."""
        config = {
            "pfmea_gate": {"severity_range": [1, 10]},
            "control_plan_gate": {},
        }
        errors = validate_config(config)
        self.assertIn(
            "Missing required configuration section: pfd_gate", errors
        )

    def test_missing_pfmea_gate_returns_error(self):
        """Omitting 'pfmea_gate' should produce a validation error."""
        config = {
            "pfd_gate": {"min_process_steps": 3},
            "control_plan_gate": {},
        }
        errors = validate_config(config)
        self.assertIn(
            "Missing required configuration section: pfmea_gate", errors
        )

    def test_missing_control_plan_gate_returns_error(self):
        """Omitting 'control_plan_gate' should produce a validation error."""
        config = {
            "pfd_gate": {"min_process_steps": 3},
            "pfmea_gate": {"severity_range": [1, 10]},
        }
        errors = validate_config(config)
        self.assertIn(
            "Missing required configuration section: control_plan_gate",
            errors,
        )

    def test_missing_all_required_sections_returns_multiple_errors(self):
        """Omitting all required sections should return error for each."""
        errors = validate_config({})
        self.assertGreaterEqual(len(errors), 3)

    def test_min_process_steps_wrong_type_returns_error(self):
        """pfd_gate.min_process_steps with non-int type should produce an error."""
        config = {
            "pfd_gate": {
                "min_process_steps": "three",
                "evidence_coverage_threshold": 0.7,
            },
            "pfmea_gate": {"severity_range": [1, 10]},
            "control_plan_gate": {},
        }
        errors = validate_config(config)
        self.assertIn(
            "pfd_gate.min_process_steps must be an integer", errors
        )

    def test_evidence_coverage_threshold_below_zero_returns_error(self):
        """evidence_coverage_threshold < 0 should produce a validation error."""
        config = {
            "pfd_gate": {
                "min_process_steps": 3,
                "evidence_coverage_threshold": -0.1,
            },
            "pfmea_gate": {"severity_range": [1, 10]},
            "control_plan_gate": {},
        }
        errors = validate_config(config)
        self.assertTrue(
            any(
                "evidence_coverage_threshold" in err
                and "between 0 and 1" in err
                for err in errors
            ),
            msg=f"Expected threshold range error, got {errors}",
        )

    def test_evidence_coverage_threshold_above_one_returns_error(self):
        """evidence_coverage_threshold > 1 should produce a validation error."""
        config = {
            "pfd_gate": {
                "min_process_steps": 3,
                "evidence_coverage_threshold": 1.5,
            },
            "pfmea_gate": {"severity_range": [1, 10]},
            "control_plan_gate": {},
        }
        errors = validate_config(config)
        self.assertTrue(
            any(
                "evidence_coverage_threshold" in err
                and "between 0 and 1" in err
                for err in errors
            ),
        )

    def test_severity_range_not_a_list_returns_error(self):
        """pfmea_gate.severity_range that is not a list should produce an error."""
        config = {
            "pfd_gate": {"min_process_steps": 3},
            "pfmea_gate": {"severity_range": "invalid"},
            "control_plan_gate": {},
        }
        errors = validate_config(config)
        self.assertIn(
            "pfmea_gate.severity_range must be a list of [min, max]", errors
        )

    def test_severity_range_wrong_length_returns_error(self):
        """pfmea_gate.severity_range with length != 2 should produce an error."""
        config = {
            "pfd_gate": {"min_process_steps": 3},
            "pfmea_gate": {"severity_range": [1, 5, 10]},
            "control_plan_gate": {},
        }
        errors = validate_config(config)
        self.assertIn(
            "pfmea_gate.severity_range must be a list of [min, max]", errors
        )


class GetDefaultConfigTest(unittest.TestCase):
    """Tests for get_default_config()."""

    def test_returns_dict_with_all_required_sections(self):
        """get_default_config() should return a dict with every expected gate section."""
        config = get_default_config()

        self.assertIn("pfd_gate", config)
        self.assertIn("pfmea_gate", config)
        self.assertIn("control_plan_gate", config)
        self.assertIn("linkage_requirements", config)
        self.assertIn("export_gate", config)

    def test_pfd_gate_has_reasonable_defaults(self):
        """Default PFD gate config should have sensible values."""
        config = get_default_config()
        pfd = config["pfd_gate"]

        self.assertIsInstance(pfd["min_process_steps"], int)
        self.assertGreater(pfd["min_process_steps"], 0)
        self.assertIsInstance(pfd["evidence_coverage_threshold"], float)
        self.assertGreaterEqual(pfd["evidence_coverage_threshold"], 0)
        self.assertLessEqual(pfd["evidence_coverage_threshold"], 1)
        self.assertIn("operation", pfd["required_fields"])
        self.assertIn("process_function", pfd["required_fields"])

    def test_pfmea_gate_has_reasonable_defaults(self):
        """Default PFMEA gate config should have sensible values."""
        config = get_default_config()
        pfmea = config["pfmea_gate"]

        self.assertIsInstance(pfmea["min_failure_modes"], int)
        self.assertGreaterEqual(pfmea["min_failure_modes"], 1)
        self.assertEqual(pfmea["severity_range"], [1, 10])
        self.assertIsInstance(pfmea["required_controls"], bool)
        self.assertIn("failure_mode", pfmea["required_fields"])
        self.assertIn("severity", pfmea["required_fields"])

    def test_control_plan_gate_has_reasonable_defaults(self):
        """Default Control Plan gate config should have sensible values."""
        config = get_default_config()
        cp = config["control_plan_gate"]

        self.assertIsInstance(cp["min_control_items"], int)
        self.assertGreaterEqual(cp["min_control_items"], 1)
        self.assertIn("control_characteristic", cp["required_fields"])
        self.assertIn("control_method", cp["required_fields"])
        self.assertIn("acceptance_criteria", cp["required_fields"])

    def test_self_validation_passes(self):
        """The built-in default config should always pass its own validation."""
        config = get_default_config()
        errors = validate_config(config)
        self.assertEqual(
            errors,
            [],
            msg=f"Default config should have zero validation errors, got: {errors}",
        )


class SectionAccessorsTest(unittest.TestCase):
    """Tests for get_pfd_config, get_pfmea_config, etc."""

    def test_get_pfd_config_returns_pfd_section(self):
        """get_pfd_config should return the PFD gate sub-dict when given a full config."""
        config = get_default_config()
        pfd = get_pfd_config(config)
        self.assertEqual(pfd, config["pfd_gate"])

    def test_get_pfmea_config_returns_pfmea_section(self):
        """get_pfmea_config should return the PFMEA gate sub-dict when given a full config."""
        config = get_default_config()
        pfmea = get_pfmea_config(config)
        self.assertEqual(pfmea, config["pfmea_gate"])

    def test_get_pfd_config_without_arg_loads_default(self):
        """get_pfd_config called without argument should not raise."""
        pfd = get_pfd_config()
        self.assertIsInstance(pfd, dict)
        self.assertIn("min_process_steps", pfd)

    def test_get_pfmea_config_without_arg_loads_default(self):
        """get_pfmea_config called without argument should not raise."""
        pfmea = get_pfmea_config()
        self.assertIsInstance(pfmea, dict)
        self.assertIn("min_failure_modes", pfmea)


class IntegrationWithRealConfigFileTest(unittest.TestCase):
    """Tests that load the actual config/quality_gates.yaml from the repo."""

    def test_real_config_file_exists_and_is_valid(self):
        """The project's own quality_gates.yaml should be loadable and pass validation."""
        config_path = get_default_config_path()

        self.assertTrue(
            config_path.exists(),
            msg=f"Default config file should exist at {config_path}",
        )

        config = load_quality_gate_config(str(config_path))
        errors = validate_config(config)

        self.assertEqual(
            errors,
            [],
            msg=f"Real config file should have zero validation errors, got: {errors}",
        )

    def test_real_config_has_all_expected_gate_sections(self):
        """The project's quality_gates.yaml should define all gate sections used by the codebase."""
        config_path = get_default_config_path()
        config = load_quality_gate_config(str(config_path))

        self.assertIn("pfd_gate", config)
        self.assertIn("pfmea_gate", config)
        self.assertIn("control_plan_gate", config)
        self.assertIn("linkage_requirements", config)
        self.assertIn("export_gate", config)
        self.assertIn("reporting", config)


if __name__ == "__main__":
    unittest.main()
