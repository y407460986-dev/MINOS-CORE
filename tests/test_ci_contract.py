"""Contract checks for the dependency surfaces used by GitHub Actions."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _load_workflow() -> dict:
    with WORKFLOW.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _run_steps(job: dict) -> list[str]:
    return [str(step.get("run", "")) for step in job.get("steps", [])]


def _step(job: dict, *, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_project_declares_test_tools_and_yaml_stub() -> None:
    with PYPROJECT.open("rb") as stream:
        project = tomllib.load(stream)["project"]["optional-dependencies"]

    assert {item.split(">=", 1)[0] for item in project["test"]} == {
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
        "diff-cover",
    }
    assert any(item.startswith("types-PyYAML>=") for item in project["dev"])


def test_python_jobs_install_their_runtime_dependency_surfaces() -> None:
    jobs = _load_workflow()["jobs"]

    for job_name in ("python-quality", "python-tests", "real-acceptance"):
        runs = "\n".join(_run_steps(jobs[job_name]))
        assert "pip install -r requirements/locks/linux-py311.txt" in runs
        assert "pip install -e . --no-deps" in runs


def test_python_tests_prepare_frontend_before_running_pytest() -> None:
    jobs = _load_workflow()["jobs"]
    test_job = jobs["python-tests"]
    setup_node = _step(test_job, name="Set up Node")

    assert setup_node["uses"] == "actions/setup-node@v4"
    assert str(setup_node["with"]["node-version"]) == "20"

    npm_ci_index = next(
        index
        for index, step in enumerate(test_job["steps"])
        if "npm ci" in str(step.get("run", ""))
    )
    pytest_index = next(
        index
        for index, step in enumerate(test_job["steps"])
        if "python -m pytest" in str(step.get("run", ""))
    )
    assert npm_ci_index < pytest_index
    assert test_job["steps"][npm_ci_index]["working-directory"] == "apps/desktop-tauri"

    runs = "\n".join(_run_steps(test_job))
    assert "import keyring, sse_starlette, fitz, rapidocr_onnxruntime" in runs
    assert "python -m pip check" in runs


def test_python_tests_and_dependency_checks_are_hard_gates() -> None:
    jobs = _load_workflow()["jobs"]

    assert all("continue-on-error" not in step for step in jobs["python-tests"]["steps"])
    for name in ("pip-audit", "Check Python dependencies", "Repository hygiene"):
        assert "continue-on-error" not in _step(jobs["python-quality"], name=name)

    npm_audit = _step(jobs["desktop-quality"], name="npm audit")
    assert "--audit-level=high" in npm_audit["run"]
    assert "continue-on-error" not in npm_audit


def test_python_tests_enforce_total_coverage_floor() -> None:
    jobs = _load_workflow()["jobs"]
    pytest_run = _step(jobs["python-tests"], name="Run pytest")["run"]

    for source in ("minos_core", "minos_desktop", "minos_platform"):
        assert f"--cov={source}" in pytest_run
    assert "--cov-report=xml" in pytest_run
    assert "--cov-fail-under=80" in pytest_run

    with PYPROJECT.open("rb") as stream:
        coverage = tomllib.load(stream)["tool"]["coverage"]["report"]
    assert coverage["fail_under"] == 80


def test_real_acceptance_runs_the_explicit_unittest_file() -> None:
    step = _step(_load_workflow()["jobs"]["real-acceptance"], name="Run real API acceptance tests")
    assert step["run"] == "python -m pytest tests/acceptance/test_real_api_acceptance.py -q"


@pytest.mark.parametrize(
    "job_name",
    [
        "windows-dependency-lock",
        "python-quality",
        "python-tests",
        "desktop-quality",
        "real-acceptance",
    ],
)
def test_ci_checkouts_fetch_full_history(job_name: str) -> None:
    checkout = _step(_load_workflow()["jobs"][job_name], name="Checkout")
    assert checkout["uses"] == "actions/checkout@v4"
    assert str(checkout["with"]["fetch-depth"]) == "0"
