from __future__ import annotations

from unittest.mock import Mock, patch

from minos_platform.cli import main


def test_platform_cli_help_returns_zero_without_starting_server(capsys):
    with patch("minos_platform.cli.subprocess.run") as run:
        result = main(["--help"])

    captured = capsys.readouterr()
    assert result == 0
    assert "usage:" in captured.out
    run.assert_not_called()


def test_platform_cli_default_port_is_passed_as_text():
    completed = Mock(returncode=0)
    with patch("minos_platform.cli.subprocess.run", return_value=completed) as run:
        result = main([])

    assert result == 0
    command = run.call_args.args[0]
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "8000"
    assert all(isinstance(value, str) for value in command)


def test_platform_cli_parses_host_and_port():
    completed = Mock(returncode=0)
    with patch("minos_platform.cli.subprocess.run", return_value=completed) as run:
        result = main(["--host", "0.0.0.0", "--port", "8010"])

    assert result == 0
    command = run.call_args.args[0]
    assert command[command.index("--host") + 1] == "0.0.0.0"
    assert command[command.index("--port") + 1] == "8010"
