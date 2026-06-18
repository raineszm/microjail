"""Tests for CLI output formatting under non-TTY streams.

The CLI is invoked through ``typer.testing.CliRunner`` (which captures
stdout/stderr as non-TTY streams), so the assertions below exercise the
real output path — not the private ``_output`` helpers.
"""

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from microjail.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_validate_writes_checkmark_to_stdout(microjail_project: Path) -> None:
    result = CliRunner().invoke(app, ["validate"])

    assert result.exit_code == 0, result.stderr
    assert "✓" in result.stdout
    assert "\x1b[" not in result.stdout


def test_status_writes_info_verbatim_to_stdout(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["--project", str(tmp_path), "status"])

    assert result.exit_code == 0
    assert "Not initialized" in result.stdout
    assert "\x1b[" not in result.stdout


def test_destroy_writes_error_prefix_to_stderr(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["--project", str(tmp_path), "destroy"])

    assert result.exit_code == 1
    assert "✗ error:" in result.stderr
    assert "\x1b[" not in result.stderr


def test_init_overwrite_writes_warning_prefix_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Stub the system-boundary ``workshop init`` subprocess so the test
    # stays a unit test; the warning itself fires before that call.
    def noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("microjail.adapters.workshop.Workshop.init", noop)

    result = CliRunner().invoke(
        app, ["--project", str(tmp_path), "init", "missing-ws", "--overwrite"]
    )

    assert "⚠ warning:" in result.stderr
    assert "\x1b[" not in result.stderr
