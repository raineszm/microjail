import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from microjail.adapters.workshop import WorkshopNotLaunchedError
from microjail.gates.network_drop import NetworkDrop
from microjail.microjail import MicroJail

WORKSHOP_NAME = "mj-workshop"
PROJECT = Path("/project")


def gate() -> NetworkDrop:
    return NetworkDrop()


def test_network_drop_has_gate_name() -> None:
    assert gate().name == "network-egress"


async def test_check_returns_false_when_egress_probe_succeeds() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.exec_ = AsyncMock(
        return_value=subprocess.CompletedProcess(args=[], returncode=0)
    )

    assert not await gate().check(mock_mj)

    mock_mj.exec_.assert_called_once_with(
        ["bash", "-c", ": >/dev/tcp/1.1.1.1/443"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


async def test_check_returns_true_when_egress_probe_fails() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.exec_ = AsyncMock(
        return_value=subprocess.CompletedProcess(args=[], returncode=1)
    )

    assert await gate().check(mock_mj)


async def test_enforce_removes_all_network_devices_from_workshop_container() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance = AsyncMock(
        return_value=SimpleNamespace(
            devices={
                "root": {"type": "disk", "path": "/"},
                "eth0": {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
                "uplink": {"type": "nic", "nictype": "bridged", "parent": "fan0"},
            }
        )
    )
    mock_mj.remove_device = AsyncMock()

    await gate().enforce(mock_mj)

    assert mock_mj.remove_device.mock_calls == [
        call("eth0"),
        call("uplink"),
    ]


async def test_release_restores_network_devices_removed_by_enforce() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance = AsyncMock(
        return_value=SimpleNamespace(
            devices={
                "root": {"type": "disk", "path": "/"},
                "eth0": {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
            }
        )
    )
    mock_mj.remove_device = AsyncMock()
    mock_mj.add_device = AsyncMock()

    network_gate = gate()
    await network_gate.enforce(mock_mj)
    await network_gate.release(mock_mj)

    mock_mj.add_device.assert_called_once_with(
        "eth0",
        {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
    )


async def test_release_restores_workshop_when_removed_network_device_cannot_be_derived() -> (
    None
):
    mock_mj = Mock(spec=MicroJail)
    mock_mj.profile_devices = AsyncMock(return_value={})
    mock_mj.restore_workshop = AsyncMock()
    mock_mj.add_device = AsyncMock()

    network_gate = gate()
    await network_gate.release(mock_mj)

    mock_mj.restore_workshop.assert_called_once_with()
    mock_mj.add_device.assert_not_called()


async def test_enforce_fails_if_workshop_container_is_not_available() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance = AsyncMock(
        side_effect=WorkshopNotLaunchedError(
            name=WORKSHOP_NAME,
            project=PROJECT,
        )
    )

    with pytest.raises(WorkshopNotLaunchedError) as exc_info:
        await gate().enforce(mock_mj)

    assert exc_info.value.name == WORKSHOP_NAME
    assert exc_info.value.project == PROJECT
