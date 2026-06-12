import subprocess
from unittest.mock import Mock, call

import pytest

from microjail.microjail import MicroJail
from microjail.warden import CapabilityPolicyViolation, GatePolicyViolation, Warden


def test_warden_supervises_successful_exit() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.return_value = 0

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    mock_process.wait.assert_called_once_with(timeout=0.01)


def test_warden_supervises_non_zero_exit() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.return_value = 42

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 42
    mock_process.wait.assert_called_once_with(timeout=0.01)


def test_warden_polls_on_interval() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    mock_gate.check.return_value = True

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = True

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = [mock_cap]

    mock_process = Mock(spec=subprocess.Popen)
    # We raise TimeoutExpired twice, then exit with 0
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    assert mock_gate.check.call_count == 2
    assert mock_cap.check.call_count == 2
    mock_gate.check.assert_has_calls([call(mock_mj), call(mock_mj)])
    mock_cap.check.assert_has_calls([call(mock_mj), call(mock_mj)])


def test_warden_terminates_on_gate_violation() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    # Returns True on first check, False on second
    mock_gate.check.side_effect = [True, False]

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = True

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = [mock_cap]
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = Mock(spec=subprocess.Popen)
    # Wait times out twice (we need it to poll twice to see the check change)
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    # Check that process termination was called
    mock_process.terminate.assert_called_once()
    # Wait should be called to wait for process termination with timeout of 2 seconds
    mock_process.wait.assert_any_call(timeout=2)


def test_warden_terminates_on_gate_violation_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    mock_gate.check.return_value = False

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = []
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = Mock(spec=subprocess.Popen)
    # First wait times out (initiates policy check)
    # During terminate, we wait again, which also times out (escalation)
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        subprocess.TimeoutExpired(cmd="terminate", timeout=2),
    ]

    mock_stop_instance = Mock()
    monkeypatch.setattr(
        "microjail.adapters.lxc.stop_instance", mock_stop_instance, raising=False
    )

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    # Check process termination and container stop
    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)
    mock_stop_instance.assert_called_once_with(
        "test-container", "test-project", force=True
    )


def test_warden_warns_on_non_fatal_capability_violation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = False
    mock_cap.fatal = False

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = [mock_cap]

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    mock_process.terminate.assert_not_called()

    captured = capsys.readouterr()
    assert "Warning: Capability policy violation" in captured.err
    assert "mock-cap" in captured.err


def test_warden_terminates_on_fatal_capability_violation() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = False
    mock_cap.fatal = True

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = [mock_cap]
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act & Assert
    with pytest.raises(CapabilityPolicyViolation):
        warden.supervise()

    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)
