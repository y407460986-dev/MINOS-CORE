"""Tests for the desktop sidecar command-line launcher."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from minos_desktop.api import cli

app_module = importlib.import_module("minos_desktop.api.app")


@pytest.mark.parametrize(
    ("argv", "environment_token", "generated_token", "expected_token"),
    [
        (["--token", "argument-token"], None, "generated", "argument-token"),
        ([], "environment-token", "generated", "environment-token"),
        ([], None, "generated-token", "generated-token"),
    ],
)
def test_main_configures_app_token_and_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    argv: list[str],
    environment_token: str | None,
    generated_token: str,
    expected_token: str,
) -> None:
    db_path = tmp_path / "desktop.sqlite3"
    output_dir = tmp_path / "out"
    fake_app = object()
    calls: dict[str, object] = {}

    if environment_token is None:
        monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", "")
    else:
        monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", environment_token)
    monkeypatch.setattr(cli.secrets, "token_urlsafe", lambda _length: generated_token)
    monkeypatch.setattr(
        app_module,
        "create_app",
        lambda *, db_path, output_dir: calls.update(db_path=db_path, output_dir=output_dir) or fake_app,
    )

    import uvicorn

    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **kwargs: calls.update(app=app, uvicorn=SimpleNamespace(**kwargs)),
    )

    exit_code = cli.main(
        [
            *argv,
            "--host",
            "127.0.0.2",
            "--port",
            "8123",
            "--db-path",
            str(db_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert cli.os.environ["MINOS_DESKTOP_API_TOKEN"] == expected_token
    assert calls["db_path"] == db_path
    assert calls["output_dir"] == output_dir
    assert calls["app"] is fake_app
    assert calls["uvicorn"].host == "127.0.0.2"
    assert calls["uvicorn"].port == 8123
    assert calls["uvicorn"].log_level == "info"
