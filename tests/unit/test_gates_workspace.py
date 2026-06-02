"""Unit tests for the workspace-mounted gate.

Constitution requirement: tests MUST demonstrate the gate BLOCKS when the
workspace is not mounted inside the container.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from microjail.gates import GateResult
from microjail.gates.workspace import check_workspace_mounted

_CONTAINER = "test-env"
_PROJECT = "workshop.abc123"
_WORKSPACE = Path("/home/user/myproject")


def _mock_project() -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = f"{_PROJECT},active\n".encode()
    m.stderr = b""
    return m


def _mock_device_show(output: str) -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = output.encode()
    m.stderr = b""
    return m


_DEVICE_WITH_WORKSPACE = f"""workspace:
  path: /root/myproject
  source: {_WORKSPACE}
  type: disk
"""

_DEVICE_WITHOUT_WORKSPACE = """eth0:
  name: eth0
  type: nic
"""


@patch("subprocess.run")
def test_workspace_mounted_gate_passes_when_present(mock_run: MagicMock) -> None:
    """Gate PASSES when the workspace is listed as a mounted device."""
    mock_run.side_effect = [_mock_project(), _mock_device_show(_DEVICE_WITH_WORKSPACE)]
    result = check_workspace_mounted(_CONTAINER, _WORKSPACE)
    assert isinstance(result, GateResult)
    assert result.passed is True
    assert result.name == "workspace-mounted"


@patch("subprocess.run")
def test_workspace_mounted_gate_blocks_when_absent(mock_run: MagicMock) -> None:
    """Gate FAILS (blocks workload) when workspace is not in the device config.

    Constitution-mandated blocking case.
    """
    mock_run.side_effect = [
        _mock_project(),
        _mock_device_show(_DEVICE_WITHOUT_WORKSPACE),
    ]
    result = check_workspace_mounted(_CONTAINER, _WORKSPACE)
    assert result.passed is False
    assert str(_WORKSPACE) in result.message


@patch("subprocess.run")
def test_workspace_mounted_gate_fails_on_lxc_error(mock_run: MagicMock) -> None:
    """Gate FAILS when lxc config device show returns a non-zero exit code."""
    fail = MagicMock()
    fail.returncode = 1
    fail.stdout = b""
    fail.stderr = b"error: container not found"
    mock_run.side_effect = [_mock_project(), fail]
    result = check_workspace_mounted(_CONTAINER, _WORKSPACE)
    assert result.passed is False
    assert "container not found" in result.message
