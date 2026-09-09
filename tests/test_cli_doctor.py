"""Behavior tests for the environment diagnostics command."""

from __future__ import annotations

import builtins
from types import SimpleNamespace

import pytest

from minos_core import ai_config, cli_doctor


def test_diagnostic_check_formats_known_and_unknown_statuses() -> None:
    assert str(cli_doctor.DiagnosticCheck("Python", "ok", "ready")) == "[OK] Python: ready"
    assert str(cli_doctor.DiagnosticCheck("Plugin", "custom", "state", "details")) == (
        "[?] Plugin: state\n   details"
    )


def test_python_version_reports_supported_and_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    assert cli_doctor.check_python_version().status == "ok"

    monkeypatch.setattr(cli_doctor.sys, "version_info", SimpleNamespace(major=3, minor=10, micro=9))
    check = cli_doctor.check_python_version()
    assert check.status == "error"
    assert "requires >= 3.11" in check.message


def test_ocr_engine_checks_cover_missing_available_and_import_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from minos_core import ocr_detection

    monkeypatch.setattr(ocr_detection, "detect_available_ocr_engines", lambda: [])
    missing = cli_doctor.check_ocr_engines()
    assert [check.status for check in missing] == ["error", "warning"]

    monkeypatch.setattr(ocr_detection, "detect_available_ocr_engines", lambda: ["rapidocr", "mineru"])
    monkeypatch.setattr(cli_doctor.shutil, "which", lambda _command: "C:/tools/magic-pdf.exe")
    available = cli_doctor.check_ocr_engines()
    assert [check.status for check in available] == ["ok", "ok"]
    assert "magic-pdf.exe" in available[1].message

    real_import = builtins.__import__

    def fail_rapidocr_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "rapidocr_onnxruntime":
            raise ImportError("broken runtime")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_rapidocr_import)
    failed = cli_doctor.check_ocr_engines()
    assert failed[0].status == "warning"
    assert failed[0].details == "broken runtime"


def test_ai_config_checks_supported_loader_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ai_config,
        "load_ai_config",
        lambda: SimpleNamespace(base_url="https://primary.example/v1"),
        raising=False,
    )
    assert cli_doctor.check_ai_config().status == "ok"

    monkeypatch.delattr(ai_config, "load_ai_config", raising=False)
    monkeypatch.setattr(ai_config, "get_ai_config", lambda: SimpleNamespace(base_url=""), raising=False)
    assert cli_doctor.check_ai_config().status == "warning"

    monkeypatch.delattr(ai_config, "get_ai_config", raising=False)
    monkeypatch.setattr(
        ai_config,
        "AIConfig",
        lambda: SimpleNamespace(base_url="https://fallback.example/v1"),
        raising=False,
    )
    assert cli_doctor.check_ai_config().status == "ok"

    monkeypatch.setattr(ai_config, "AIConfig", lambda: (_ for _ in ()).throw(RuntimeError("bad config")))
    failed = cli_doctor.check_ai_config()
    assert failed.status == "warning"
    assert failed.details == "bad config"


def test_backup_endpoint_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINOS_BACKUP_AI_ENDPOINTS", raising=False)
    assert cli_doctor.check_backup_endpoints().status == "warning"

    monkeypatch.setenv("MINOS_BACKUP_AI_ENDPOINTS", "https://one.example,https://two.example")
    configured = cli_doctor.check_backup_endpoints()
    assert configured.status == "ok"
    assert configured.message.startswith("2 backup endpoint")


def test_dependency_checks_report_imported_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def import_dependency(name: str) -> object:
        if name == "pymupdf":
            raise ImportError(name)
        return SimpleNamespace(__version__="1.2.3")

    monkeypatch.setattr(cli_doctor.importlib, "import_module", import_dependency)
    checks = cli_doctor.check_dependencies()
    assert [check.status for check in checks] == ["ok", "ok", "error"]
    assert "version 1.2.3" in checks[0].message


@pytest.mark.parametrize(
    ("free_gb", "expected"),
    [(11, "ok"), (6, "warning"), (5, "error")],
)
def test_disk_space_thresholds(
    monkeypatch: pytest.MonkeyPatch, free_gb: int, expected: str
) -> None:
    monkeypatch.setattr(cli_doctor.shutil, "disk_usage", lambda _path: (0, 0, free_gb * 2**30))
    assert cli_doctor.check_disk_space().status == expected


def test_disk_space_failure_is_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_doctor.shutil,
        "disk_usage",
        lambda _path: (_ for _ in ()).throw(OSError("unavailable")),
    )
    check = cli_doctor.check_disk_space()
    assert check.status == "warning"
    assert check.details == "unavailable"


def test_run_diagnostics_assembles_all_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = cli_doctor.DiagnosticCheck("ok", "ok", "ready")
    warning = cli_doctor.DiagnosticCheck("warning", "warning", "review")
    monkeypatch.setattr(cli_doctor, "check_python_version", lambda: ok)
    monkeypatch.setattr(cli_doctor, "check_disk_space", lambda: ok)
    monkeypatch.setattr(cli_doctor, "check_dependencies", lambda: [ok])
    monkeypatch.setattr(cli_doctor, "check_ocr_engines", lambda: [warning])
    monkeypatch.setattr(cli_doctor, "check_ai_config", lambda: warning)
    monkeypatch.setattr(cli_doctor, "check_backup_endpoints", lambda: warning)

    assert cli_doctor.run_diagnostics() == [ok, ok, ok, warning, warning, warning]


@pytest.mark.parametrize(("status", "exit_code"), [("error", 1), ("warning", 0), ("ok", 0)])
def test_print_diagnostics_exit_codes(status: str, exit_code: int) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_doctor.print_diagnostics([cli_doctor.DiagnosticCheck("check", status, "message")])
    assert exc_info.value.code == exit_code


def test_print_diagnostics_can_return_without_exit() -> None:
    cli_doctor.print_diagnostics(
        [cli_doctor.DiagnosticCheck("check", "error", "message")],
        exit_on_complete=False,
    )


def test_print_config_sources_logs_formatted_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    from minos_core.observability import config_diagnostics

    monkeypatch.setattr(config_diagnostics, "describe_config_sources", lambda: {"source": "env"})
    monkeypatch.setattr(config_diagnostics, "format_config_sources", lambda sources: f"formatted:{sources['source']}")
    cli_doctor.print_config_sources()


def test_doctor_command_runs_sections_before_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    checks = [cli_doctor.DiagnosticCheck("check", "ok", "ready")]
    calls: list[object] = []
    monkeypatch.setattr(cli_doctor, "run_diagnostics", lambda: checks)
    monkeypatch.setattr(
        cli_doctor,
        "print_diagnostics",
        lambda value, *, exit_on_complete: calls.append((value, exit_on_complete)),
    )
    monkeypatch.setattr(cli_doctor, "print_config_sources", lambda: calls.append("sources"))
    monkeypatch.setattr(cli_doctor, "_exit_after_diagnostics", lambda value: calls.append(value))

    cli_doctor.doctor_command()

    assert calls == [(checks, False), "sources", checks]


@pytest.mark.parametrize(("status", "exit_code"), [("error", 1), ("warning", 0)])
def test_exit_after_diagnostics(status: str, exit_code: int) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_doctor._exit_after_diagnostics([cli_doctor.DiagnosticCheck("check", status, "message")])
    assert exc_info.value.code == exit_code
