from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest  # noqa: TC002
from typer.testing import CliRunner

from microjail.cli import app
from microjail.lockdown import GateError
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


def fail_lockdown(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    ensure = MagicMock(side_effect=failure)
    monkeypatch.setattr(MicroJail, "ensure", ensure)


def test_run_requires_workload_command(microjail_project: Path) -> None:
    result = CliRunner().invoke(app, ["run"])

    assert result.exit_code != 0
    assert "command" in result.stderr.lower()


def test_run_propagates_workload_exit_status(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    def ensure(self: MicroJail) -> None:
        assert self.project_path == microjail_project

    monkeypatch.setattr(MicroJail, "ensure", ensure)
    monkeypatch.setattr(
        MicroJail,
        "exec_",
        lambda _self, cmd, **_kw: __import__("subprocess").run(cmd, check=False),
    )

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "exit 7"])

    assert result.exit_code == 7


def test_run_reports_lockdown_failure_without_starting_workload(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    fail_lockdown(monkeypatch, GateError(name="network-egress"))

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "echo started"])

    assert result.exit_code == 1
    assert "network-egress" in result.stderr
    assert "started" not in result.stdout
