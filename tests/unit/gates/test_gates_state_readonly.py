"""Unit tests for the state-readonly gate.

Constitution requirement: tests MUST demonstrate the gate BLOCKS when the
readonly=true device is absent.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from microjail.gates import GateResult
from microjail.gates.state_readonly import _STATE_RO_DEVICE, check_state_readonly

_CONTAINER = "test-env"
_PROJECT = "workshop.abc123"
_WORKSPACE = Path("/home/user/myproject")


def _mock_project() -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = f"{_PROJECT},active\n".encode()
    m.stderr = b""
    return m


def _device_show(output: str) -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = output.encode()
    m.stderr = b""
    return m


_WITH_READONLY_DEVICE = f"""{_STATE_RO_DEVICE}:
  path: /root/myproject/.microjail/state.json
  readonly: "true"
  source: /home/user/myproject/.microjail/state.json
  type: disk
"""

_WITHOUT_READONLY_DEVICE = """workspace:
  path: /root/myproject
  source: /home/user/myproject
  type: disk
"""

_DEVICE_WITHOUT_READONLY_FLAG = f"""{_STATE_RO_DEVICE}:
  path: /root/myproject/.microjail/state.json
  source: /home/user/myproject/.microjail/state.json
  type: disk
"""


@patch("subprocess.run")
def test_state_readonly_gate_passes_when_device_present(mock_run: MagicMock) -> None:
    """Gate PASSES when the readonly=true device is present and confirmed."""
    mock_run.side_effect = [_mock_project(), _device_show(_WITH_READONLY_DEVICE)]
    result = check_state_readonly(_CONTAINER, _WORKSPACE)
    assert isinstance(result, GateResult)
    assert result.passed is True
    assert result.name == "state-readonly"


@patch("subprocess.run")
def test_state_readonly_gate_blocks_when_device_absent(mock_run: MagicMock) -> None:
    """Gate FAILS (blocks workload) when the readonly device is not present.

    Constitution-mandated blocking case: state file is writable from inside
    the container.
    """
    mock_run.side_effect = [_mock_project(), _device_show(_WITHOUT_READONLY_DEVICE)]
    result = check_state_readonly(_CONTAINER, _WORKSPACE)
    assert result.passed is False
    assert _STATE_RO_DEVICE in result.message


@patch("subprocess.run")
def test_state_readonly_gate_blocks_when_readonly_flag_missing(
    mock_run: MagicMock,
) -> None:
    """Gate FAILS when device is present but readonly flag is not set."""
    mock_run.side_effect = [
        _mock_project(),
        _device_show(_DEVICE_WITHOUT_READONLY_FLAG),
    ]
    result = check_state_readonly(_CONTAINER, _WORKSPACE)
    assert result.passed is False
    assert "readonly=true is not set" in result.message


@patch("subprocess.run")
def test_state_readonly_gate_fails_on_lxc_error(mock_run: MagicMock) -> None:
    """Gate FAILS when lxc config device show errors."""
    fail = MagicMock()
    fail.returncode = 1
    fail.stdout = b""
    fail.stderr = b"error"
    mock_run.side_effect = [_mock_project(), fail]
    result = check_state_readonly(_CONTAINER, _WORKSPACE)
    assert result.passed is False
