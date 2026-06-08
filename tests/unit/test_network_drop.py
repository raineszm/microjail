import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

import microjail.gates.network_drop as network_drop
from microjail.adapters import workshop
from microjail.gates.network_drop import NetworkDrop
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail

PROJECT = Path("/project")
WORKSHOP_NAME = "mj-workshop"
CONTAINER_NAME = "mj-workshop-abc123"
LXD_PROJECT = "workshop.test-user"


def gate() -> NetworkDrop:
    return NetworkDrop()


def microjail() -> MicroJail:
    return MicroJail(
        name=WORKSHOP_NAME,
        project_path=PROJECT,
        lockdown=Lockdown(caps=[], gates=[]),
    )


def patch_container_lookup(monkeypatch: pytest.MonkeyPatch):
    get_container = Mock(return_value=workshop.ContainerInfo(name=CONTAINER_NAME))
    lxd_project = Mock(return_value=LXD_PROJECT)
    monkeypatch.setattr(network_drop.workshop, "get_container", get_container)
    monkeypatch.setattr(network_drop.workshop, "lxd_project", lxd_project)
    return get_container, lxd_project


def patch_lxc_instance(
    monkeypatch: pytest.MonkeyPatch, devices: dict[str, dict[str, str]]
):
    get_instance = Mock(return_value=SimpleNamespace(devices=devices))
    monkeypatch.setattr(network_drop.lxc, "get_instance", get_instance)
    return get_instance


def test_network_drop_has_gate_name() -> None:
    assert gate().name == "network-egress"


def test_check_returns_false_when_egress_probe_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exec_ = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0))
    monkeypatch.setattr(network_drop.workshop, "exec_", exec_)
    context = microjail()

    assert not gate().check(context)

    exec_.assert_called_once_with(
        WORKSHOP_NAME,
        PROJECT,
        ["bash", "-c", ": >/dev/tcp/1.1.1.1/443"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_check_returns_true_when_egress_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exec_ = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=1))
    monkeypatch.setattr(network_drop.workshop, "exec_", exec_)

    assert gate().check(microjail())


def test_enforce_removes_all_network_devices_from_workshop_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_container_lookup(monkeypatch)
    patch_lxc_instance(
        monkeypatch,
        {
            "root": {"type": "disk", "path": "/"},
            "eth0": {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
            "uplink": {"type": "nic", "nictype": "bridged", "parent": "fan0"},
        },
    )
    remove_device = Mock()
    monkeypatch.setattr(network_drop.lxc, "remove_device", remove_device)

    gate().enforce(microjail())

    assert remove_device.mock_calls == [
        call(CONTAINER_NAME, "eth0", project=LXD_PROJECT),
        call(CONTAINER_NAME, "uplink", project=LXD_PROJECT),
    ]


def test_release_restores_network_devices_removed_by_enforce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_container_lookup(monkeypatch)
    patch_lxc_instance(
        monkeypatch,
        {
            "root": {"type": "disk", "path": "/"},
            "eth0": {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
        },
    )
    monkeypatch.setattr(network_drop.lxc, "remove_device", Mock())
    add_device = Mock()
    monkeypatch.setattr(network_drop.lxc, "add_device", add_device)
    network_gate = gate()
    context = microjail()

    network_gate.enforce(context)
    network_gate.release(context)

    add_device.assert_called_once_with(
        CONTAINER_NAME,
        "eth0",
        {"type": "nic", "nictype": "bridged", "parent": "lxdbr0"},
        project=LXD_PROJECT,
    )


def test_enforce_fails_if_workshop_container_is_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_container = Mock(return_value=None)
    monkeypatch.setattr(network_drop.workshop, "get_container", get_container)

    with pytest.raises(workshop.WorkshopNotLaunchedError) as exc_info:
        gate().enforce(microjail())

    assert exc_info.value.name == WORKSHOP_NAME
    assert exc_info.value.project == PROJECT
