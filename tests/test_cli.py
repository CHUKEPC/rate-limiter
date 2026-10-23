"""Tests for the rate-limiter CLI commands."""

from typer.testing import CliRunner

from rate_limiter.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    """Test CLI help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CLI tool for testing" in result.stdout


def test_cli_algorithms() -> None:
    """Test CLI algorithms comparison table output."""
    result = runner.invoke(app, ["algorithms"])
    assert result.exit_code == 0
    assert "Token Bucket" in result.stdout
    assert "Sliding Window Counter" in result.stdout


def test_cli_simulation_test() -> None:
    """Test running traffic simulation from CLI."""
    result = runner.invoke(
        app,
        [
            "test",
            "--algorithm",
            "fixed_window",
            "--limit",
            "2",
            "--period",
            "5",
            "--requests",
            "3",
            "--delay",
            "0",
            "--key",
            "cli:test:key",
        ],
    )
    assert result.exit_code == 0
    assert "Simulation Results" in result.stdout
    assert "Allowed" in result.stdout


def test_cli_simulation_invalid_algorithm() -> None:
    """Test error handling on invalid algorithm name."""
    result = runner.invoke(app, ["test", "--algorithm", "nonexistent_algorithm"])
    assert result.exit_code != 0
    assert "Error: Invalid algorithm" in result.stdout


def test_cli_reset() -> None:
    """Test CLI reset command."""
    result = runner.invoke(app, ["reset", "cli:test:key"])
    assert result.exit_code == 0
    assert "Successfully reset" in result.stdout
