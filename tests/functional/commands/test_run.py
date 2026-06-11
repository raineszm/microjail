from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail import policy
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    MicroJail,
)
from tests.functional.commands.helpers import (
    RecordingCapability,
    RecordingGate,
    completed_process,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def load_as(microjail: MicroJail, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", Mock())


def test_run_requires_workload_command(microjail_project: Path) -> None:
    result = CliRunner().invoke(app, ["run"])

    assert result.exit_code != 0
    assert "command" in result.stderr.lower()


def test_run_propagates_workload_exit_status(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)
    exec_ = Mock(return_value=completed_process(7))
    monkeypatch.setattr(MicroJail, "exec_", exec_)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "exit 7"])

    assert result.exit_code == 7
    exec_.assert_called_once_with(["sh", "-c", "exit 7"], check=False)


def test_run_capability_failure_blocks_workload_and_skips_gates(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    cap = RecordingCapability("local-inference", checks=[False, False])
    gate = RecordingGate("network-egress", checks=[False, True])
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    load_as(microjail, monkeypatch)
    exec_ = Mock(return_value=completed_process(0))
    monkeypatch.setattr(MicroJail, "exec_", exec_)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "echo started"])

    assert result.exit_code == policy.CAPABILITY_APPLICATION_FAILURE
    assert "local-inference" in result.stderr
    assert "started" not in result.stdout
    assert gate.calls == []
    exec_.assert_not_called()


def test_run_gate_failure_blocks_workload(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    gate = RecordingGate("network-egress", checks=[False, False])
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=[gate]),
    )
    load_as(microjail, monkeypatch)
    exec_ = Mock(return_value=completed_process(0))
    monkeypatch.setattr(MicroJail, "exec_", exec_)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "echo started"])

    assert result.exit_code == policy.GATE_APPLICATION_FAILURE
    assert "network-egress" in result.stderr
    assert "started" not in result.stdout
    exec_.assert_not_called()


def test_run_rolls_back_applied_policy_on_pre_workload_failure(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    cap = RecordingCapability("endpoint", checks=[False, True])
    gate = RecordingGate("network-egress", checks=[False, False])
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", Mock())

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.GATE_APPLICATION_FAILURE

    assert cap.calls == ["check", "provide", "check", "revoke"]
    assert gate.calls == ["check", "enforce", "check", "release"]
