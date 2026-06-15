from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

from typer.testing import CliRunner

from microjail import policy
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    MicroJail,
)
from tests.functional.commands.helpers import RecordingCapability, RecordingGate

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from microjail.gates.base import Gate


def load_as(microjail: MicroJail, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", AsyncMock())


def test_lock_reports_success_with_counts(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    gates: list[Gate] = [
        RecordingGate("network-egress", checks=[True]),
        RecordingGate("readonly-config", checks=[True]),
    ]
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=gates),
    )
    load_as(microjail, monkeypatch)

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert "lock applied" in result.stdout
    assert "0 capabilities" in result.stdout
    assert "2 gates" in result.stdout


def test_lock_rejects_unexpected_arguments() -> None:
    result = CliRunner().invoke(app, ["lock", "workload"])

    assert result.exit_code != 0
    assert "unexpected" in result.stderr.lower()


def test_lock_capability_failure_still_attempts_gate_enforcement(
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

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == policy.CAPABILITY_APPLICATION_FAILURE
    assert "lock incomplete" in result.stderr
    assert "1 capability failures" in result.stderr
    assert "1 gates enforced" in result.stderr
    assert gate.calls == ["check", "enforce", "check"]


def test_lock_gate_failure_reports_name_and_exit_code(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    gate = RecordingGate("network-egress", checks=[False, False])
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=[gate]),
    )
    load_as(microjail, monkeypatch)

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == policy.GATE_APPLICATION_FAILURE
    assert "lock failed" in result.stderr
    assert "network-egress" in result.stderr
    assert "GateError" not in result.stderr


async def test_lock_does_not_rollback_successfully_applied_policy_after_failure(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    cap = RecordingCapability("endpoint", checks=[False, True])
    gate = RecordingGate("network-egress", checks=[False, False])
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", AsyncMock())

    result = await microjail.ensure(ApplicationIntent.LOCK)

    assert result.status is ApplicationStatus.GATE_APPLICATION_FAILURE
    assert result.gate_failure is not None
    assert cap.calls == ["check", "provide", "check"]
    assert gate.calls == ["check", "enforce", "check"]
