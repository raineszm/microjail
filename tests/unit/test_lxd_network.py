"""Unit tests for LXD network egress control.

Mocks internal helpers to simulate LXD device enumeration and container
status without requiring a live LXD installation.
"""

from unittest.mock import MagicMock, patch

import pytest

from microjail.lxd.network import lock_egress, unlock_egress

_WORKSPACE = "/tmp/workspace"
_CONTAINER = "workshop.123-myproject"
_PROJECT = "workshop.abc123"


def _mock_device_show(*devices: str) -> MagicMock:
    """Return a mock for ``lxc config device show`` with given device names.

    Each device name is treated as a NIC device.
    """
    m = MagicMock()
    m.returncode = 0
    lines = []
    for d in devices:
        lines.extend((f"{d}:", "  type: nic"))
    m.stdout = "\n".join(lines).encode()
    m.stderr = b""
    return m


def _mock_ok() -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = b""
    m.stderr = b""
    return m


def _mock_fail(stderr: str = "error") -> MagicMock:
    m = MagicMock()
    m.returncode = 1
    m.stdout = b""
    m.stderr = stderr.encode()
    return m


# ---------------------------------------------------------------------------
# lock_egress
# ---------------------------------------------------------------------------


@patch("subprocess.run")
@patch("microjail.lxd.network._workshop_project", return_value=_PROJECT)
@patch("microjail.lxd.network._container_name", return_value=_CONTAINER)
@patch("microjail.lxd.network._workspace_mount_path", return_value="/root/myproject")
def test_lock_egress_clears_routes_on_all_nics(
    mock_mount: MagicMock,
    mock_container: MagicMock,
    mock_project: MagicMock,
    mock_run: MagicMock,
) -> None:
    """lock_egress clears ipv4/ipv6 routes on every NIC device."""
    mock_run.side_effect = [
        _mock_device_show("eth0", "eth1"),
        _mock_ok(),  # eth0 ipv4
        _mock_ok(),  # eth0 ipv6
        _mock_ok(),  # eth1 ipv4
        _mock_ok(),  # eth1 ipv6
        _mock_ok(),  # readonly state.json
    ]

    lock_egress("myproject", MagicMock())

    calls = mock_run.call_args_list
    # Verify config device set calls for both NICs
    set_calls = [c for c in calls if len(c.args[0]) > 6 and c.args[0][5] == "set"]
    assert len(set_calls) == 4  # 2 NICs x 2 keys
    nic_names = {c.args[0][7] for c in set_calls}
    assert nic_names == {"eth0", "eth1"}


@patch("subprocess.run")
@patch("microjail.lxd.network._workshop_project", return_value=_PROJECT)
@patch("microjail.lxd.network._container_name", return_value=_CONTAINER)
@patch("microjail.lxd.network._workspace_mount_path", return_value="/root/myproject")
def test_lock_egress_raises_on_nic_config_failure(
    mock_mount: MagicMock,
    mock_container: MagicMock,
    mock_project: MagicMock,
    mock_run: MagicMock,
) -> None:
    """lock_egress raises RuntimeError if clearing routes on any NIC fails."""
    mock_run.side_effect = [
        _mock_device_show("eth0", "eth1"),
        _mock_ok(),  # eth0 ipv4
        _mock_ok(),  # eth0 ipv6
        _mock_fail("device not found"),  # eth1 ipv4 fails
    ]

    with pytest.raises(RuntimeError, match="Failed to cut egress"):
        lock_egress("myproject", MagicMock())


# ---------------------------------------------------------------------------
# unlock_egress
# ---------------------------------------------------------------------------


@patch("subprocess.run")
@patch("microjail.lxd.network._workshop_project", return_value=_PROJECT)
@patch("microjail.lxd.network._container_name", return_value=_CONTAINER)
def test_unlock_egress_restores_routes_on_all_nics(
    mock_container: MagicMock,
    mock_project: MagicMock,
    mock_run: MagicMock,
) -> None:
    """unlock_egress restores ipv4/ipv6 routes on every NIC device."""
    mock_run.side_effect = [
        _mock_device_show("eth0", "eth1"),
        _mock_ok(),  # readonly state.json remove
        _mock_ok(),  # eth0 ipv4
        _mock_ok(),  # eth0 ipv6
        _mock_ok(),  # eth1 ipv4
        _mock_ok(),  # eth1 ipv6
        _mock_ok(),  # info -> running
        _mock_ok(),  # network attach workshopbr0
    ]

    unlock_egress("myproject")

    calls = mock_run.call_args_list
    unset_calls = [c for c in calls if len(c.args[0]) > 6 and c.args[0][5] == "unset"]
    assert len(unset_calls) == 4  # 2 NICs x 2 keys
    nic_names = {c.args[0][7] for c in unset_calls}
    assert nic_names == {"eth0", "eth1"}


@patch("subprocess.run")
@patch("microjail.lxd.network._workshop_project", return_value=_PROJECT)
@patch("microjail.lxd.network._container_name", return_value=_CONTAINER)
def test_unlock_egress_survives_individual_failures(
    mock_container: MagicMock,
    mock_project: MagicMock,
    mock_run: MagicMock,
) -> None:
    """unlock_egress raises RuntimeError aggregating all individual failures."""
    mock_run.side_effect = [
        _mock_device_show("eth0"),
        _mock_ok(),  # readonly state.json remove
        _mock_fail("cannot unset"),  # ipv4 fails
        _mock_ok(),  # ipv6
    ]

    with pytest.raises(RuntimeError, match="Unlock completed with errors"):
        unlock_egress("myproject")
