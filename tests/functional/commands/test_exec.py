from typing import TYPE_CHECKING
from unittest.mock import Mock

from typer.testing import CliRunner

from microjail import policy
from microjail.adapters.workshop import Workshop
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
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", Mock())
    monkeypatch.setattr(
        MicroJail, "workshop_info", Mock(return_value=Mock(status="ready"))
    )


def test_exec_requires_workload_command(microjail_project: Path) -> None:
    result = CliRunner().invoke(app, ["exec"])

    assert result.exit_code != 0
    assert "command" in result.stderr.lower()


def test_exec_propagates_workload_exit_status(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)
    mock_process = Mock()
    popen = Mock(return_value=mock_process)
    monkeypatch.setattr(MicroJail, "popen", popen)
    supervise = Mock(return_value=7)
    monkeypatch.setattr(Warden, "supervise", supervise)

    result = CliRunner().invoke(app, ["exec", "--", "sh", "-c", "exit 7"])

    assert result.exit_code == 7
    popen.assert_called_once_with(["sh", "-c", "exit 7"], interactive=False)
    supervise.assert_called_once()


def test_exec_capability_failure_blocks_workload_and_skips_gates(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    class FailingProvideCapability(RecordingCapability):
        def provide(self, microjail: object, batch: object = None) -> None:
            del microjail, batch
            self.calls.append("provide")
            raise RuntimeError("provision failed")

    cap = FailingProvideCapability("local-inference", checks=[False])
    gate = RecordingGate("network-egress", checks=[False, True])
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    load_as(microjail, monkeypatch)
    popen = Mock()
    monkeypatch.setattr(MicroJail, "popen", popen)

    result = CliRunner().invoke(app, ["exec", "--", "sh", "-c", "echo started"])

    assert result.exit_code == policy.CAPABILITY_APPLICATION_FAILURE
    assert "local-inference" in result.stderr
    assert "started" not in result.stdout
    assert gate.calls == []
    popen.assert_not_called()


def test_exec_gate_failure_blocks_workload(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    gate = RecordingGate("network-egress", checks=[False, False])
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[gate]),
    )
    load_as(microjail, monkeypatch)
    popen = Mock()
    monkeypatch.setattr(MicroJail, "popen", popen)

    result = CliRunner().invoke(app, ["exec", "--", "sh", "-c", "echo started"])

    assert result.exit_code == policy.GATE_APPLICATION_FAILURE
    assert "network-egress" in result.stderr
    assert "started" not in result.stdout
    popen.assert_not_called()


def test_exec_rolls_back_applied_policy_on_pre_workload_failure(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    cap = RecordingCapability("endpoint", checks=[False, True])
    gate = RecordingGate("network-egress", checks=[False, False])
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", Mock())

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.GATE_APPLICATION_FAILURE

    assert cap.calls == ["check", "provide", "revoke"]
    assert gate.calls == ["check", "enforce", "check", "release"]


def test_exec_uses_warden_supervision(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)

    mock_process = Mock()
    mock_popen = Mock(return_value=mock_process)
    monkeypatch.setattr(MicroJail, "popen", mock_popen)

    mock_supervise = Mock(return_value=0)
    monkeypatch.setattr(Warden, "supervise", mock_supervise)

    result = CliRunner().invoke(app, ["exec", "--", "sh", "-c", "exit 0"])

    assert result.exit_code == 0
    mock_popen.assert_called_once_with(["sh", "-c", "exit 0"], interactive=False)
    mock_supervise.assert_called_once()


def test_exec_exits_with_84_on_gate_violation(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)

    mock_process = Mock()
    monkeypatch.setattr(MicroJail, "popen", Mock(return_value=mock_process))

    def raising_supervise(self):
        raise GatePolicyViolation("mock gate violation")

    monkeypatch.setattr(Warden, "supervise", raising_supervise)

    result = CliRunner().invoke(app, ["exec", "--", "sh", "-c", "exit 0"])

    assert result.exit_code == 84


def test_exec_exits_with_82_on_fatal_capability_violation(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)

    mock_process = Mock()
    monkeypatch.setattr(MicroJail, "popen", Mock(return_value=mock_process))

    def raising_supervise(self):
        raise CapabilityPolicyViolation("mock cap violation")

    monkeypatch.setattr(Warden, "supervise", raising_supervise)

    result = CliRunner().invoke(app, ["exec", "--", "sh", "-c", "exit 0"])

    assert result.exit_code == 82


def test_exec_launches_workshop_if_not_launched(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))

    mock_workshop_info = Mock(return_value=None)
    monkeypatch.setattr(MicroJail, "workshop_info", mock_workshop_info)

    mock_launch = Mock()
    monkeypatch.setattr(Workshop, "launch", mock_launch)

    # Mock popen, Warden supervise, ensure_lockdown to do nothing/success
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", Mock())
    monkeypatch.setattr("microjail.commands.exec.ensure_lockdown", Mock())
    monkeypatch.setattr(MicroJail, "popen", Mock())
    monkeypatch.setattr(Warden, "supervise", Mock(return_value=0))

    result = CliRunner().invoke(app, ["exec", "--", "true"])

    assert result.exit_code == 0
    mock_workshop_info.assert_called_once()
    mock_launch.assert_called_once()


def test_exec_remains_non_interactive_by_default(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)
    mock_process = Mock()
    popen = Mock(return_value=mock_process)
    monkeypatch.setattr(MicroJail, "popen", popen)
    monkeypatch.setattr(Warden, "supervise", Mock(return_value=0))

    result = CliRunner().invoke(app, ["exec", "--", "bash"])

    assert result.exit_code == 0
    popen.assert_called_once_with(["bash"], interactive=False)
