"""
Environment diagnostics command for MINOS-CORE.

Checks system configuration, dependencies, and provides recommendations
for optimal setup.
"""

import importlib
import os
import shutil
import sys

import structlog

logger = structlog.get_logger(__name__)


class DiagnosticCheck:
    """Represents a single diagnostic check."""

    def __init__(
        self,
        name: str,
        status: str,
        message: str,
        details: str | None = None,
    ):
        self.name = name
        self.status = status  # "ok", "warning", "error"
        self.message = message
        self.details = details

    def __str__(self) -> str:
        """Format check result for display."""
        # Use ASCII-safe symbols for Windows compatibility
        symbols = {"ok": "[OK]", "warning": "[WARN]", "error": "[ERROR]"}
        symbol = symbols.get(self.status, "[?]")
        result = f"{symbol} {self.name}: {self.message}"
        if self.details:
            result += f"\n   {self.details}"
        return result


def check_python_version() -> DiagnosticCheck:
    """Check Python version."""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version.major == 3 and version.minor >= 11:
        return DiagnosticCheck(
            "Python Version",
            "ok",
            f"Python {version_str}",
        )
    else:
        return DiagnosticCheck(
            "Python Version",
            "error",
            f"Python {version_str} (requires >= 3.11)",
        )


def check_ocr_engines() -> list[DiagnosticCheck]:
    """Check available OCR engines."""
    from minos_core.ocr_detection import (
        detect_available_ocr_engines,
    )

    checks = []
    available = detect_available_ocr_engines()

    # Check RapidOCR
    if "rapidocr" in available:
        try:
            import rapidocr_onnxruntime

            version = getattr(rapidocr_onnxruntime, "__version__", "unknown")
            checks.append(
                DiagnosticCheck(
                    "RapidOCR",
                    "ok",
                    f"Installed (version {version})",
                )
            )
        except Exception as e:
            checks.append(
                DiagnosticCheck(
                    "RapidOCR",
                    "warning",
                    "Detected but cannot import",
                    str(e),
                )
            )
    else:
        checks.append(
            DiagnosticCheck(
                "RapidOCR",
                "error",
                "Not installed",
                "Install with: pip install rapidocr-onnxruntime",
            )
        )

    # Check MinerU
    if "mineru" in available:
        mineru_cmd = shutil.which("magic-pdf") or os.getenv("MINERU_COMMAND")
        checks.append(
            DiagnosticCheck(
                "MinerU",
                "ok",
                f"Installed (command: {mineru_cmd})",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                "MinerU",
                "warning",
                "Not found (optional)",
                "MinerU provides higher accuracy OCR but is optional",
            )
        )

    return checks


def check_ai_config() -> DiagnosticCheck:
    """Check AI service configuration."""
    try:
        from minos_core import ai_config

        # Try to get AI config - different projects may have different methods
        config = None
        if hasattr(ai_config, "load_ai_config"):
            config = ai_config.load_ai_config()
        elif hasattr(ai_config, "get_ai_config"):
            config = ai_config.get_ai_config()
        elif hasattr(ai_config, "AIConfig"):
            # Try to instantiate directly
            config = ai_config.AIConfig()

        if config and hasattr(config, "base_url") and config.base_url:
            return DiagnosticCheck(
                "AI Configuration",
                "ok",
                f"Primary endpoint: {config.base_url}",
            )
        else:
            return DiagnosticCheck(
                "AI Configuration",
                "warning",
                "Configuration loaded but no endpoint found",
            )

    except Exception as e:
        # AI config errors are warnings, not critical errors
        return DiagnosticCheck(
            "AI Configuration",
            "warning",
            "Could not verify AI configuration",
            str(e),
        )


def check_backup_endpoints() -> DiagnosticCheck:
    """Check if backup AI endpoints are configured."""
    # This is a placeholder - actual implementation depends on how
    # backup endpoints are configured in the system
    backup_env = os.getenv("MINOS_BACKUP_AI_ENDPOINTS")

    if backup_env:
        endpoints = backup_env.split(",")
        return DiagnosticCheck(
            "Backup AI Endpoints",
            "ok",
            f"{len(endpoints)} backup endpoint(s) configured",
        )
    else:
        return DiagnosticCheck(
            "Backup AI Endpoints",
            "warning",
            "No backup endpoints configured",
            "Consider configuring backup endpoints for resilience",
        )


def check_dependencies() -> list[DiagnosticCheck]:
    """Check core dependencies."""
    checks = []

    # SECURITY FIX v3.1.0: Whitelist of allowed packages for diagnostics
    allowed_packages = {
        "httpx", "pydantic", "pymupdf", "structlog", "fastapi",
        "uvicorn", "sqlalchemy", "aiosqlite", "pillow",
        "rapidocr_onnxruntime", "onnxruntime"
    }

    dependencies = [
        ("httpx", "HTTP client"),
        ("pydantic", "Data validation"),
        ("PyMuPDF", "PDF processing"),
    ]

    for package, description in dependencies:
        package_normalized = package.lower().replace("-", "_")

        if package_normalized not in allowed_packages:
            checks.append(
                DiagnosticCheck(
                    package,
                    "error",
                    f"{description} - NOT ALLOWED (security policy)",
                )
            )
            continue

        try:
            module = importlib.import_module(package_normalized)
            version = getattr(module, "__version__", "unknown")
            checks.append(
                DiagnosticCheck(
                    package,
                    "ok",
                    f"{description} (version {version})",
                )
            )
        except ImportError:
            checks.append(
                DiagnosticCheck(
                    package,
                    "error",
                    f"{description} not installed",
                )
            )

    return checks


def check_disk_space() -> DiagnosticCheck:
    """Check available disk space."""
    try:
        import shutil

        total, used, free = shutil.disk_usage("/")
        free_gb = free // (2**30)

        if free_gb > 10:
            return DiagnosticCheck(
                "Disk Space",
                "ok",
                f"{free_gb} GB available",
            )
        elif free_gb > 5:
            return DiagnosticCheck(
                "Disk Space",
                "warning",
                f"{free_gb} GB available (low)",
            )
        else:
            return DiagnosticCheck(
                "Disk Space",
                "error",
                f"{free_gb} GB available (critically low)",
            )
    except Exception as e:
        return DiagnosticCheck(
            "Disk Space",
            "warning",
            "Could not check disk space",
            str(e),
        )


def run_diagnostics() -> list[DiagnosticCheck]:
    """
    Run all diagnostic checks.

    Returns:
        List of diagnostic check results
    """
    checks = []

    # System checks
    checks.append(check_python_version())
    checks.append(check_disk_space())

    # Dependency checks
    checks.extend(check_dependencies())

    # OCR checks
    checks.extend(check_ocr_engines())

    # AI configuration checks
    checks.append(check_ai_config())
    checks.append(check_backup_endpoints())

    return checks


def print_diagnostics(
    checks: list[DiagnosticCheck],
    *,
    exit_on_complete: bool = True,
) -> None:
    """
    Print diagnostic results to console.

    Args:
        checks: List of diagnostic check results
        exit_on_complete: When True (default) the function calls ``sys.exit``
            so this function is suitable as a CLI entry point. Pass False when
            additional sections will be printed after the summary.
    """
    logger.info("diagnostics_header", separator="=" * 60)
    logger.info("diagnostics_title", title="MINOS-CORE Environment Diagnostics")
    logger.info("diagnostics_header", separator="=" * 60)

    # Group by status
    ok_checks = [c for c in checks if c.status == "ok"]
    warning_checks = [c for c in checks if c.status == "warning"]
    error_checks = [c for c in checks if c.status == "error"]

    # Print all checks
    for check in checks:
        logger.info("diagnostic_check", check=str(check))

    # Summary
    logger.info("diagnostics_separator", separator="-" * 60)
    logger.info("diagnostics_summary", ok=len(ok_checks), warnings=len(warning_checks), errors=len(error_checks))

    if error_checks:
        logger.error("diagnostics_critical_issues", message="Critical issues found. Please address errors above.")
        if exit_on_complete:
            sys.exit(1)
    elif warning_checks:
        logger.warning(
            "diagnostics_warnings_found",
            message="Some warnings found. System should work but may not be optimal.",
        )
        if exit_on_complete:
            sys.exit(0)
    else:
        logger.info("diagnostics_all_passed", message="All checks passed!")
        if exit_on_complete:
            sys.exit(0)


def doctor_command() -> None:
    """Main entry point for the doctor command."""
    checks = run_diagnostics()
    print_diagnostics(checks, exit_on_complete=False)
    print_config_sources()
    _exit_after_diagnostics(checks)


def print_config_sources() -> None:
    """Print configuration provenance information."""

    try:
        from minos_core.observability.config_diagnostics import (
            describe_config_sources,
            format_config_sources,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.warning("config_sources_unavailable", error=str(exc))
        return

    sources = describe_config_sources()
    logger.info("config_sources_separator", separator="-" * 60)
    logger.info("config_sources_title", title="Configuration Sources")
    logger.info("config_sources_separator", separator="-" * 60)
    logger.info("config_sources_details", sources=format_config_sources(sources))


def _exit_after_diagnostics(checks: list[DiagnosticCheck]) -> None:
    """Apply the original diagnostic exit codes after extra sections print."""

    error_checks = [c for c in checks if c.status == "error"]
    if error_checks:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    doctor_command()
