"""
Quality gate configuration loader.

Loads and validates quality gate configuration from YAML files,
allowing business rules to be externalized and modified without code changes.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_default_config_path() -> Path:
    """
    Get the default path to the quality gates configuration file.

    Returns:
        Path to config/quality_gates.yaml
    """
    # Try to find config relative to this file
    module_dir = Path(__file__).parent
    config_path = module_dir.parent.parent / "config" / "quality_gates.yaml"

    if config_path.exists():
        return config_path

    # Fall back to current working directory
    cwd_config = Path.cwd() / "config" / "quality_gates.yaml"
    if cwd_config.exists():
        return cwd_config

    # Return default path even if it doesn't exist
    # (caller will handle missing file)
    return config_path


def load_quality_gate_config(path: str | Path | None = None) -> dict[str, Any]:
    """
    Load quality gate configuration from YAML file.

    Args:
        path: Optional path to configuration file. If None, uses default location.

    Returns:
        Dictionary containing quality gate configuration

    Raises:
        FileNotFoundError: If configuration file is not found
        ValueError: If configuration is invalid
    """
    if path is None:
        path = get_default_config_path()
    else:
        path = Path(path)

    if not path.exists():
        logger.warning(f"Quality gate config not found at {path}, using defaults")
        return get_default_config()

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        logger.info(f"Loaded quality gate config from {path}")
        return config

    except ImportError:
        logger.error("PyYAML not installed, using default configuration")
        return get_default_config()

    except Exception as e:
        logger.error(f"Failed to load quality gate config from {path}: {e}")
        raise ValueError(f"Invalid quality gate configuration: {e}") from e


def get_default_config() -> dict[str, Any]:
    """
    Get default quality gate configuration.

    Returns:
        Dictionary with default configuration values
    """
    return {
        "pfd_gate": {
            "min_process_steps": 3,
            "required_fields": ["operation", "process_function"],
            "evidence_coverage_threshold": 0.7,
        },
        "pfmea_gate": {
            "min_failure_modes": 1,
            "severity_range": [1, 10],
            "occurrence_range": [1, 10],
            "detection_range": [1, 10],
            "required_controls": True,
            "required_fields": [
                "failure_mode",
                "failure_effect",
                "severity",
                "occurrence",
                "detection",
            ],
        },
        "control_plan_gate": {
            "min_control_items": 1,
            "required_fields": [
                "control_characteristic",
                "control_method",
                "sample_size",
                "sample_frequency",
                "acceptance_criteria",
            ],
        },
        "linkage_requirements": {
            "pfd_to_pfmea": {
                "min_coverage": 0.8,
                "allow_unlinked_pfmea": True,
            },
            "pfmea_to_cp": {
                "require_controls_for_high_risk": True,
                "control_required_rpn": 100,
                "allow_unlinked_controls": True,
            },
        },
        "export_gate": {
            "require_all_gates_pass": True,
            "allow_export_with_warnings": True,
            "require_evidence_attachments": False,
            "min_evidence_coverage": 0.6,
        },
    }


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    Validate quality gate configuration.

    Args:
        config: Configuration dictionary to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check required top-level keys
    required_keys = ["pfd_gate", "pfmea_gate", "control_plan_gate"]
    for key in required_keys:
        if key not in config:
            errors.append(f"Missing required configuration section: {key}")

    # Validate PFD gate
    if "pfd_gate" in config:
        pfd = config["pfd_gate"]
        if "min_process_steps" in pfd and not isinstance(
            pfd["min_process_steps"], int
        ):
            errors.append("pfd_gate.min_process_steps must be an integer")
        if "evidence_coverage_threshold" in pfd:
            threshold = pfd["evidence_coverage_threshold"]
            if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
                errors.append(
                    "pfd_gate.evidence_coverage_threshold must be between 0 and 1"
                )

    # Validate PFMEA gate
    if "pfmea_gate" in config:
        pfmea = config["pfmea_gate"]
        if "severity_range" in pfmea:
            if not isinstance(pfmea["severity_range"], list) or len(
                pfmea["severity_range"]
            ) != 2:
                errors.append("pfmea_gate.severity_range must be a list of [min, max]")

    return errors


def get_pfd_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Get PFD quality gate configuration.

    Args:
        config: Optional full configuration. If None, loads from default location.

    Returns:
        PFD gate configuration
    """
    if config is None:
        config = load_quality_gate_config()
    return config.get("pfd_gate", get_default_config()["pfd_gate"])


def get_pfmea_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Get PFMEA quality gate configuration.

    Args:
        config: Optional full configuration. If None, loads from default location.

    Returns:
        PFMEA gate configuration
    """
    if config is None:
        config = load_quality_gate_config()
    return config.get("pfmea_gate", get_default_config()["pfmea_gate"])


def get_control_plan_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Get Control Plan quality gate configuration.

    Args:
        config: Optional full configuration. If None, loads from default location.

    Returns:
        Control Plan gate configuration
    """
    if config is None:
        config = load_quality_gate_config()
    return config.get(
        "control_plan_gate", get_default_config()["control_plan_gate"]
    )


def get_export_gate_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Get export gate configuration.

    Args:
        config: Optional full configuration. If None, loads from default location.

    Returns:
        Export gate configuration
    """
    if config is None:
        config = load_quality_gate_config()
    return config.get("export_gate", get_default_config()["export_gate"])
