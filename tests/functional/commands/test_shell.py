from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from microjail import policy
from microjail.adapters.workshop import Workshop
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail
from microjail.warden import CapabilityPolicyViolation, GatePolicyViolation, Warden
from tests.functional.commands.helpers import RecordingCapability, RecordingGate

if TYPE_CHECKING:
    from pathlib import Path


def load_as(microjail: MicroJail, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MicroJail, "load", Mock(return_value=microjail))
    monkeypatch.setattr(MicroJail, "ensure_workshop_ready", Mock())
    monkeypatch.setattr(
        MicroJail, "workshop_info", Mock(return_value=Mock(status="ready"))
    )


def allow_interactive_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "microjail.commands.shell.stdin_is_tty", Mock(return_value=True)
    )
    monkeypatch.setattr(
        "microjail.commands.shell.stdout_is_tty", Mock(return_value=True)
    )


def test_shell_applies_lockdown_then_starts_default_shell_interactively(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    events: list[str] = []
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)

    def record_lockdown(microjail: MicroJail) -> None:
        events.append("lockdown")

    mock_process = Mock()

    def record_shell() -> Mock:
        events.append("shell")
        return mock_process

    allow_interactive_terminal(monkeypatch)
    monkeypatch.setattr("microjail.commands.shell.ensure_lockdown", record_lockdown)
    shell = Mock(side_effect=record_shell)
    monkeypatch.setattr(MicroJail, "shell", shell)
    supervised_processes = []

    def supervise_warden(warden: Warden) -> int:
        supervised_processes.append(warden.process)
        return 0

    monkeypatch.setattr(Warden, "supervise", supervise_warden)

    result = CliRunner().invoke(app, ["shell"])

    assert result.exit_code == 0
    assert events == ["lockdown", "shell"]
    shell.assert_called_once_with()
    assert supervised_processes == [mock_process]


def test_shell_uses_explicit_command_interactively(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)
    allow_interactive_terminal(monkeypatch)
    monkeypatch.setattr("microjail.commands.shell.ensure_lockdown", Mock())
    mock_process = Mock()
    popen = Mock(return_value=mock_process)
    monkeypatch.setattr(MicroJail, "popen", popen)
    monkeypatch.setattr(Warden, "supervise", Mock(return_value=0))

    result = CliRunner().invoke(app, ["shell", "--", "bash", "-l"])

    assert result.exit_code == 0
    popen.assert_called_once_with(["bash", "-l"], interactive=True)


def test_shell_capability_failure_blocks_workload_and_skips_gates(
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
    allow_interactive_terminal(monkeypatch)
    popen = Mock()
    monkeypatch.setattr(MicroJail, "popen", popen)
    shell = Mock()
    monkeypatch.setattr(MicroJail, "shell", shell)

    result = CliRunner().invoke(app, ["shell"])

    assert result.exit_code == policy.CAPABILITY_APPLICATION_FAILURE
    assert "local-inference" in result.stderr
    assert gate.calls == []
    popen.assert_not_called()
    shell.assert_not_called()


def test_shell_gate_failure_blocks_workload(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    gate = RecordingGate("network-egress", checks=[False, False])
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[gate]),
    )
    load_as(microjail, monkeypatch)
    allow_interactive_terminal(monkeypatch)
    popen = Mock()
    monkeypatch.setattr(MicroJail, "popen", popen)
    shell = Mock()
    monkeypatch.setattr(MicroJail, "shell", shell)

    result = CliRunner().invoke(app, ["shell"])

    assert result.exit_code == policy.GATE_APPLICATION_FAILURE
    assert "network-egress" in result.stderr
    popen.assert_not_called()
    shell.assert_not_called()


def test_shell_pre_launch_verify_integration(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    from microjail.lockdown import CapabilityError, GateError
    from microjail.microjail import PreLaunchVerifyResult

    # Case 1: GateError on verification blocks the shell
    microjail = MicroJail(
        workshop=Workshop("mj-workshop", microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)
    allow_interactive_terminal(monkeypatch)
    popen = Mock()
    shell_proc = Mock()
    monkeypatch.setattr(MicroJail, "popen", popen)
    monkeypatch.setattr(MicroJail, "shell", shell_proc)

    mock_verify = Mock(side_effect=GateError(name="some-gate"))
    monkeypatch.setattr(MicroJail, "pre_launch_verify", mock_verify)

    result = CliRunner().invoke(app, ["shell"])
    assert result.exit_code == policy.GATE_APPLICATION_FAILURE
    assert "gate some-gate failed" in result.stderr
    popen.assert_not_called()
    shell_proc.assert_not_called()

    # Case 2: CapabilityError on verification blocks the shell
    mock_verify.side_effect = CapabilityError(
        name="fatal-cap", non_fatal_failures=("warn-cap",)
    )
    result = CliRunner().invoke(app, ["shell"])
    assert result.exit_code == policy.CAPABILITY_APPLICATION_FAILURE
    assert "capability fatal-cap failed" in result.stderr
    assert "warning: warn-cap" in result.stderr
    popen.assert_not_called()
    shell_proc.assert_not_called()

    # Case 3: Success with non-fatal warning
    mock_verify.side_effect = None
    mock_verify.return_value = PreLaunchVerifyResult(
        non_fatal_capability_failures=("warn-cap-only",)
    )
    mock_process = Mock()
    shell_proc.return_value = mock_process
    monkeypatch.setattr(Warden, "supervise", Mock(return_value=0))

    result = CliRunner().invoke(app, ["shell"])
    assert result.exit_code == 0
    assert "warning: warn-cap-only" in result.stderr
    shell_proc.assert_called_once()

    # Case 4: Success with unsupported verification note
    mock_verify.return_value = PreLaunchVerifyResult(
        non_fatal_capability_failures=(),
        unsupported_verifications=("some-gate-unsupported",),
    )
    result = CliRunner().invoke(app, ["shell"])
    assert result.exit_code == 0
    assert "Note: Verification not supported for some-gate-unsupported" in result.stdout
    shell_proc.assert_called()


def test_shell_propagates_workload_exit_status(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)
    allow_interactive_terminal(monkeypatch)
    mock_process = Mock()
    popen = Mock(return_value=mock_process)
    monkeypatch.setattr(MicroJail, "popen", popen)
    monkeypatch.setattr(Warden, "supervise", Mock(return_value=7))

    result = CliRunner().invoke(app, ["shell", "--", "sh", "-c", "exit 7"])

    assert result.exit_code == 7
    popen.assert_called_once_with(["sh", "-c", "exit 7"], interactive=True)


def test_shell_exits_with_84_on_gate_violation(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)
    allow_interactive_terminal(monkeypatch)
    mock_process = Mock()
    monkeypatch.setattr(MicroJail, "shell", Mock(return_value=mock_process))

    def raising_supervise(self):
        raise GatePolicyViolation("mock gate violation")

    monkeypatch.setattr(Warden, "supervise", raising_supervise)

    result = CliRunner().invoke(app, ["shell"])

    assert result.exit_code == policy.RUNTIME_GATE_POLICY_VIOLATION


def test_shell_exits_with_82_on_fatal_capability_violation(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    microjail = MicroJail(
        workshop=Workshop(name="test-jail", project=microjail_project),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    load_as(microjail, monkeypatch)
    allow_interactive_terminal(monkeypatch)
    mock_process = Mock()
    monkeypatch.setattr(MicroJail, "shell", Mock(return_value=mock_process))

    def raising_supervise(self):
        raise CapabilityPolicyViolation("mock cap violation")

    monkeypatch.setattr(Warden, "supervise", raising_supervise)

    result = CliRunner().invoke(app, ["shell"])

    assert result.exit_code == policy.FATAL_RUNTIME_CAPABILITY_VIOLATION


@pytest.mark.parametrize(
    ("stdin_is_tty", "stdout_is_tty"),
    [(False, True), (True, False)],
)
def test_shell_rejects_non_tty_before_loading_policy(
    monkeypatch: pytest.MonkeyPatch,
    stdin_is_tty: bool,
    stdout_is_tty: bool,
) -> None:
    load = Mock()
    ensure_lockdown = Mock()
    popen = Mock()
    shell = Mock()
    monkeypatch.setattr(MicroJail, "load", load)
    monkeypatch.setattr("microjail.commands.shell.ensure_lockdown", ensure_lockdown)
    monkeypatch.setattr(MicroJail, "popen", popen)
    monkeypatch.setattr(MicroJail, "shell", shell)
    monkeypatch.setattr(
        "microjail.commands.shell.stdin_is_tty", Mock(return_value=stdin_is_tty)
    )
    monkeypatch.setattr(
        "microjail.commands.shell.stdout_is_tty", Mock(return_value=stdout_is_tty)
    )

    result = CliRunner().invoke(app, ["shell"])

    assert result.exit_code != 0
    assert "interactive terminal" in result.stderr
    load.assert_not_called()
    ensure_lockdown.assert_not_called()
    popen.assert_not_called()
    shell.assert_not_called()
