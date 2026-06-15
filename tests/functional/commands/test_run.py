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
from microjail.warden import CapabilityPolicyViolation, GatePolicyViolation, Warden
from tests.functional.commands.helpers import (
    RecordingCapability,
    RecordingGate,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def load_as(microjail: MicroJail, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", AsyncMock())
    monkeypatch.setattr(
        MicroJail, "workshop_info", AsyncMock(return_value=Mock(status="ready"))
    )


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
    mock_process = Mock()
    popen = AsyncMock(return_value=mock_process)
    monkeypatch.setattr(MicroJail, "popen", popen)
    supervise = AsyncMock(return_value=7)
    monkeypatch.setattr(Warden, "supervise", supervise)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "exit 7"])

    assert result.exit_code == 7
    popen.assert_called_once_with(["sh", "-c", "exit 7"], interactive=False)
    supervise.assert_called_once()


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
    popen = AsyncMock()
    monkeypatch.setattr(MicroJail, "popen", popen)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "echo started"])

    assert result.exit_code == policy.CAPABILITY_APPLICATION_FAILURE
    assert "local-inference" in result.stderr
    assert "started" not in result.stdout
    assert gate.calls == []
    popen.assert_not_called()


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
    popen = AsyncMock()
    monkeypatch.setattr(MicroJail, "popen", popen)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "echo started"])

    assert result.exit_code == policy.GATE_APPLICATION_FAILURE
    assert "network-egress" in result.stderr
    assert "started" not in result.stdout
    popen.assert_not_called()


async def test_run_rolls_back_applied_policy_on_pre_workload_failure(
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

    result = await microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.GATE_APPLICATION_FAILURE

    assert cap.calls == ["check", "provide", "check", "revoke"]
    assert gate.calls == ["check", "enforce", "check", "release"]


def test_run_uses_warden_supervision(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)

    mock_process = Mock()
    mock_popen = AsyncMock(return_value=mock_process)
    monkeypatch.setattr(MicroJail, "popen", mock_popen)

    mock_supervise = AsyncMock(return_value=0)
    monkeypatch.setattr(Warden, "supervise", mock_supervise)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "exit 0"])

    assert result.exit_code == 0
    mock_popen.assert_called_once_with(["sh", "-c", "exit 0"], interactive=False)
    mock_supervise.assert_called_once()


def test_run_exits_with_84_on_gate_violation(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)

    mock_process = Mock()
    monkeypatch.setattr(MicroJail, "popen", AsyncMock(return_value=mock_process))

    async def raising_supervise(self):
        raise GatePolicyViolation("mock gate violation")

    monkeypatch.setattr(Warden, "supervise", raising_supervise)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "exit 0"])

    assert result.exit_code == 84


def test_run_exits_with_82_on_fatal_capability_violation(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)

    mock_process = Mock()
    monkeypatch.setattr(MicroJail, "popen", AsyncMock(return_value=mock_process))

    async def raising_supervise(self):
        raise CapabilityPolicyViolation("mock cap violation")

    monkeypatch.setattr(Warden, "supervise", raising_supervise)

    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "exit 0"])

    assert result.exit_code == 82


def test_run_launches_workshop_if_not_launched(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        name="test-jail",
        project_path=microjail_project,
        lockdown=Lockdown(caps=[], gates=[]),
    )
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))

    mock_workshop_info = AsyncMock(return_value=None)
    monkeypatch.setattr(MicroJail, "workshop_info", mock_workshop_info)

    mock_launch = AsyncMock()
    monkeypatch.setattr("microjail.adapters.workshop.launch", mock_launch)

    # Mock popen, Warden supervise, ensure_lockdown to do nothing/success
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", AsyncMock())
    monkeypatch.setattr("microjail.commands.run.ensure_lockdown", AsyncMock())
    monkeypatch.setattr(MicroJail, "popen", AsyncMock())
    monkeypatch.setattr(Warden, "supervise", AsyncMock(return_value=0))

    result = CliRunner().invoke(app, ["run", "--", "true"])

    assert result.exit_code == 0
    mock_workshop_info.assert_called_once()
    mock_launch.assert_called_once_with("test-jail", project=microjail_project)
