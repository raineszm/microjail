from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from microjail.cli import app
from microjail.lockdown import GateError
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


def create_microjail_config(project: Path) -> Path:
    config = project / ".microjail" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        f"name: test-jail\nproject_path: {project}\nlockdown:\n  caps: []\n  gates: []\n",
        encoding="utf-8",
    )
    return config


@pytest.fixture
def microjail_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    create_microjail_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def fail_lockdown(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    ensure = MagicMock(side_effect=failure)
    monkeypatch.setattr(MicroJail, "ensure", ensure)


def test_run_requires_workload_command(microjail_project: Path) -> None:
    result = CliRunner().invoke(app, ["run"])

    assert result.exit_code != 0
    assert "command" in result.stderr.lower()


def test_run_propagates_workload_exit_status(microjail_project: Path) -> None:
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
