from typing import TYPE_CHECKING

import pytest  # noqa: TC002
from typer.testing import CliRunner

from microjail.cli import app
from microjail.lockdown import CapabilityError, GateError
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


def fail_lockdown(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    def ensure(self: MicroJail) -> None:
        raise failure

    monkeypatch.setattr(MicroJail, "ensure", ensure)


def test_lock_reports_success(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    def ensure(self: MicroJail) -> None:
        assert self.project_path == microjail_project

    monkeypatch.setattr(MicroJail, "ensure", ensure)

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert "locked" in result.stdout.lower()


def test_lock_rejects_unexpected_arguments() -> None:
    result = CliRunner().invoke(app, ["lock", "workload"])

    assert result.exit_code != 0
    assert "unexpected" in result.stderr.lower()


def test_lock_warns_on_capability_failure_by_default(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    fail_lockdown(monkeypatch, CapabilityError(name="local-inference"))

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert "failed to provide capabilities" in result.stderr.lower()
    assert "local-inference" in result.stderr


def test_lock_reports_gate_failure(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    fail_lockdown(monkeypatch, GateError(name="network-egress"))

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 1
    assert "failed to enforce gates" in result.stderr.lower()
    assert "network-egress" in result.stderr
    assert "GateError" not in result.stderr
