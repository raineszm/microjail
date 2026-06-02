"""Unit tests for the egress-down gate.

Mocks ``subprocess.run`` to simulate egress reachable and egress severed
states without requiring a live LXD installation.

Constitution requirement: tests MUST demonstrate the gate BLOCKS when the
condition is not met (egress up = gate fails).
"""

from unittest.mock import MagicMock, patch

from microjail.gates import GateResult
from microjail.gates.egress import check_egress_down

_CONTAINER = "test-env"
_PROJECT = "workshop.abc123"


def _mock_project(project: str = _PROJECT) -> MagicMock:
    """Return a completed-process mock for ``lxc project list``."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = f"{project},active\n".encode()
    m.stderr = b""
    return m


def _mock_ping(returncode: int) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = b""
    m.stderr = b""
    return m


@patch("subprocess.run")
def test_egress_down_gate_passes_when_ping_fails(mock_run: MagicMock) -> None:
    """Gate PASSES when the probe cannot reach the external host (egress is down)."""
    mock_run.side_effect = [_mock_project(), _mock_ping(1)]
    result = check_egress_down(_CONTAINER)
    assert isinstance(result, GateResult)
    assert result.passed is True
    assert result.name == "egress-down"


@patch("subprocess.run")
def test_egress_down_gate_blocks_when_ping_succeeds(mock_run: MagicMock) -> None:
    """Gate FAILS (blocks workload) when egress is still reachable.

    This is the constitution-mandated blocking case: if ping succeeds,
    the gate must return passed=False so the workload is never spawned.
    """
    mock_run.side_effect = [_mock_project(), _mock_ping(0)]
    result = check_egress_down(_CONTAINER)
    assert result.passed is False
    assert "still reachable" in result.message
    assert _CONTAINER in result.message


@patch("subprocess.run")
def test_egress_down_gate_fails_when_project_unavailable(mock_run: MagicMock) -> None:
    """Gate FAILS when the LXD project cannot be determined."""
    fail = MagicMock()
    fail.returncode = 1
    fail.stdout = b""
    fail.stderr = b"error: cannot connect"
    mock_run.return_value = fail
    result = check_egress_down(_CONTAINER)
    assert result.passed is False
    assert "LXD project" in result.message
