import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

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


def test_check_returns_false_when_egress_probe_succeeds() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.exec_.return_value = subprocess.CompletedProcess(args=[], returncode=0)

    assert not gate().check(mock_mj)

    mock_mj.exec_.assert_called_once_with(
        ["bash", "-c", ": >/dev/tcp/1.1.1.1/443"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_check_returns_true_when_egress_probe_fails() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.exec_.return_value = subprocess.CompletedProcess(args=[], returncode=1)

    assert gate().check(mock_mj)


def test_enforce_removes_all_network_devices_from_workshop_container() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.return_value = SimpleNamespace(
        devices={
            "root": {"type": "disk", "path": "/"},
            "eth0": {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
            "uplink": {"type": "nic", "nictype": "bridged", "parent": "fan0"},
        }
    )

    gate().enforce(mock_mj)

    assert mock_mj.remove_device.mock_calls == [
        call("eth0"),
        call("uplink"),
    ]


def test_release_restores_network_devices_removed_by_enforce() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.return_value = SimpleNamespace(
        devices={
            "root": {"type": "disk", "path": "/"},
            "eth0": {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
        }
    )

    network_gate = gate()
    network_gate.enforce(mock_mj)
    network_gate.release(mock_mj)

    mock_mj.add_device.assert_called_once_with(
        "eth0",
        {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
    )


def test_release_restores_workshop_when_removed_network_device_cannot_be_derived() -> (
    None
):
    mock_mj = Mock(spec=MicroJail)
    mock_mj.profile_devices.return_value = {}

    network_gate = gate()
    network_gate.release(mock_mj)

    mock_mj.restore_workshop.assert_called_once()
    mock_mj.add_device.assert_not_called()


def test_enforce_fails_if_workshop_container_is_not_available() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.side_effect = WorkshopNotLaunchedError(
        name=WORKSHOP_NAME,
        project=PROJECT,
    )

    with pytest.raises(WorkshopNotLaunchedError) as exc_info:
        gate().enforce(mock_mj)

    assert exc_info.value.name == WORKSHOP_NAME
    assert exc_info.value.project == PROJECT
