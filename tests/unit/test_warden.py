from unittest.mock import AsyncMock, Mock, call

import anyio
import pytest

from microjail.microjail import MicroJail
from microjail.warden import CapabilityPolicyViolation, GatePolicyViolation, Warden


@pytest.fixture(autouse=True)
def mock_lxc_stop_instance(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr("microjail.adapters.lxc.stop_instance", mock, raising=False)
    return mock


async def test_warden_supervises_successful_exit() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    mock_process = AsyncMock()
    mock_process.wait.return_value = 0

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act
    exit_code = await warden.supervise()

    # Assert
    assert exit_code == 0
    mock_process.wait.assert_called_once()


async def test_warden_supervises_non_zero_exit() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    mock_process = AsyncMock()
    mock_process.wait.return_value = 42

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act
    exit_code = await warden.supervise()

    # Assert
    assert exit_code == 42
    mock_process.wait.assert_called_once()


async def test_warden_polls_on_interval() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = AsyncMock()
    mock_gate.name = "mock-gate"
    mock_gate.check.return_value = True

    mock_cap = AsyncMock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = True

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = [mock_cap]

    mock_process = AsyncMock()

    async def async_wait():
        await anyio.sleep(0.025)
        return 0

    mock_process.wait.side_effect = async_wait

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act
    exit_code = await warden.supervise()

    # Assert
    assert exit_code == 0
    assert mock_gate.check.call_count >= 2
    assert mock_cap.check.call_count >= 2
    mock_gate.check.assert_has_calls([call(mock_mj), call(mock_mj)])
    mock_cap.check.assert_has_calls([call(mock_mj), call(mock_mj)])


async def test_warden_terminates_on_gate_violation() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = AsyncMock()
    mock_gate.name = "mock-gate"
    mock_gate.check.side_effect = [True, False]

    mock_cap = AsyncMock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = True

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = [mock_cap]
    mock_mj.container_name = AsyncMock(return_value="test-container")
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = AsyncMock()
    mock_process.terminate = Mock()

    async def infinite_wait():
        await anyio.sleep(10)
        return 0

    mock_process.wait.side_effect = infinite_wait

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        await warden.supervise()

    # Check that process termination was called
    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call()


async def test_warden_terminates_on_gate_violation_escalation(
    mock_lxc_stop_instance,
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = AsyncMock()
    mock_gate.name = "mock-gate"
    mock_gate.check.return_value = False

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = []
    mock_mj.container_name = AsyncMock(return_value="test-container")
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = AsyncMock()
    mock_process.terminate = Mock()

    async def slow_wait():
        await anyio.sleep(10)
        return 0

    mock_process.wait.side_effect = slow_wait

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        await warden.supervise()

    # Check process termination and container stop
    mock_process.terminate.assert_called_once()
    mock_lxc_stop_instance.assert_called_once_with(
        "test-container", "test-project", force=True
    )


async def test_warden_warns_on_non_fatal_capability_violation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_cap = AsyncMock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = False
    mock_cap.fatal = False

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = [mock_cap]

    mock_process = AsyncMock()
    mock_process.terminate = Mock()

    async def async_wait():
        await anyio.sleep(0.015)
        return 0

    mock_process.wait.side_effect = async_wait

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act
    exit_code = await warden.supervise()

    # Assert
    assert exit_code == 0
    mock_process.terminate.assert_not_called()

    captured = capsys.readouterr()
    assert "Warning: Capability policy violation" in captured.err
    assert "mock-cap" in captured.err


async def test_warden_terminates_on_fatal_capability_violation() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_cap = AsyncMock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = False
    mock_cap.fatal = True

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = [mock_cap]
    mock_mj.container_name = AsyncMock(return_value="test-container")
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = AsyncMock()
    mock_process.terminate = Mock()

    async def infinite_wait():
        await anyio.sleep(10)
        return 0

    mock_process.wait.side_effect = infinite_wait

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Act & Assert
    with pytest.raises(CapabilityPolicyViolation):
        await warden.supervise()

    mock_process.terminate.assert_called_once()
