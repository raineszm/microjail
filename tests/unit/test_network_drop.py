import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, call

import pytest

from microjail.adapters.workshop import WorkshopNotLaunchedError
from microjail.gates.network_drop import NetworkDrop
from microjail.microjail import MicroJail

WORKSHOP_NAME = "mj-workshop"
PROJECT = Path("/project")


def gate() -> NetworkDrop:
    return NetworkDrop()


class FakeMicroJail:
    """Hand-rolled stand-in for MicroJail that tracks device mutations.

    Used by the release tests so we can assert on the resulting
    container state (what nics are attached, whether workshop was
    restored) rather than on call sequences.
    """

    def __init__(
        self,
        *,
        profile_devices: dict[str, dict[str, object]] | None = None,
        devices: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.profile_devices_data = (
            profile_devices if profile_devices is not None else {}
        )
        self.devices_data = devices if devices is not None else {}
        self.attached_networks: list[str] = []
        self.restored = False

    def profile_devices(self) -> dict[str, dict[str, object]]:
        return self.profile_devices_data

    def lxc_instance(self) -> SimpleNamespace:
        return SimpleNamespace(devices=self.devices_data)

    def add_device(self, device: str, config: dict[str, object]) -> None:
        self.devices_data[device] = config

    def remove_device(self, device: str) -> None:
        self.devices_data.pop(device, None)

    def attach_network(self, network: str) -> None:
        self.attached_networks.append(network)

    def restore_workshop(self) -> None:
        self.restored = True


def test_network_drop_has_gate_name() -> None:
    assert gate().name == "network-egress"


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
    mj = FakeMicroJail(
        devices={
            "root": {"type": "disk", "path": "/"},
            "eth0": {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
        }
    )

    network_gate = gate()
    network_gate.enforce(cast("MicroJail", mj))
    network_gate.release(cast("MicroJail", mj))

    # the eth0 nic that enforce() removed is back in the container's
    # device list, and we did not need to fall back to attach/restore
    assert mj.devices_data["eth0"] == {
        "type": "nic",
        "nictype": "bridged",
        "parent": "lxdbr0",
    }
    assert not mj.restored
    assert mj.attached_networks == []


def test_release_attaches_default_network_when_no_recorded_state_or_profile() -> None:
    mj = FakeMicroJail(profile_devices={}, devices={})

    gate().release(cast("MicroJail", mj))

    assert mj.attached_networks == ["workshopbr0"]
    assert not mj.restored


def test_release_falls_back_to_workshop_restore_when_attach_fails() -> None:
    from microjail.adapters.lxc import LxcCommandError

    class FailingAttachMicroJail(FakeMicroJail):
        def __init__(self) -> None:
            super().__init__(profile_devices={}, devices={})
            self.attach_calls: list[str] = []

        def attach_network(self, network: str) -> None:
            self.attach_calls.append(network)
            raise LxcCommandError(
                cmd=[
                    "lxc",
                    "network",
                    "attach",
                    network,
                    "container",
                    "--project",
                    "p",
                ],
                returncode=1,
                stderr="network not found",
            )

    mj = FailingAttachMicroJail()

    gate().release(cast("MicroJail", mj))

    # the new behaviour: try to attach workshopbr0 first, fall back to
    # workshop restore when that fails (rather than always restoring)
    assert mj.attach_calls == ["workshopbr0"]
    assert mj.restored


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


def test_network_drop_check_and_verify() -> None:
    # Case 1: check returns True when no NICs are present
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.return_value = SimpleNamespace(
        devices={"root": {"type": "disk", "path": "/"}}
    )
    assert gate().check(mock_mj) is True

    # Case 2: check returns False when NIC is present
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.return_value = SimpleNamespace(
        devices={
            "root": {"type": "disk", "path": "/"},
            "eth0": {"type": "nic", "nictype": "bridged", "parent": "workshopbr0"},
        }
    )
    assert gate().check(mock_mj) is False

    # Case 3: check returns False when container is not available
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["lxc", "query"], stderr="instance not found"
    )
    assert gate().check(mock_mj) is False

    # Case 4: verify returns UNSUPPORTED unconditionally
    from microjail.gates.base import VerificationResult

    mock_mj = Mock(spec=MicroJail)
    assert gate().verify(mock_mj) == VerificationResult.UNSUPPORTED
