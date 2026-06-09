from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest  # noqa: TC002
from typer.testing import CliRunner

from microjail.cli import app
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


def fail_release(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    release = MagicMock(side_effect=failure)
    monkeypatch.setattr(MicroJail, "release", release)


def test_unlock_reports_success(microjail_project: Path) -> None:
    result = CliRunner().invoke(app, ["unlock"])

    assert result.exit_code == 0
    assert "unlocked" in result.stdout.lower()


def test_unlock_rejects_unexpected_arguments() -> None:
    result = CliRunner().invoke(app, ["unlock", "workload"])

    assert result.exit_code != 0
    assert "unexpected" in result.stderr.lower()


def test_unlock_reports_release_failures(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    fail_release(
        monkeypatch,
        ExceptionGroup("lockdown release failures", [RuntimeError("network-egress")]),
    )

    result = CliRunner().invoke(app, ["unlock"])

    assert result.exit_code == 1
    assert "failed" in result.stderr.lower()
    assert "network-egress" in result.stderr
