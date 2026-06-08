from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import microjail.gates.readonly_config as readonly_config
from microjail.adapters import workshop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail

PROJECT = Path("/project")
WORKSHOP_NAME = "mj-workshop"
CONTAINER_NAME = "mj-workshop-abc123"
LXD_PROJECT = "workshop.test-user"


def gate() -> ReadonlyConfig:
    return ReadonlyConfig()


def microjail() -> MicroJail:
    return MicroJail(
        name=WORKSHOP_NAME,
        project_path=PROJECT,
        lockdown=Lockdown(caps=[], gates=[]),
    )


def patch_container_lookup(monkeypatch: pytest.MonkeyPatch):
    get_container = Mock(return_value=workshop.ContainerInfo(name=CONTAINER_NAME))
    lxd_project = Mock(return_value=LXD_PROJECT)
    monkeypatch.setattr(readonly_config.workshop, "get_container", get_container)
    monkeypatch.setattr(readonly_config.workshop, "lxd_project", lxd_project)
    return get_container, lxd_project


def patch_lxc_instance(
    monkeypatch: pytest.MonkeyPatch, devices: dict[str, dict[str, str]]
):
    get_instance = Mock(return_value=SimpleNamespace(devices=devices))
    monkeypatch.setattr(readonly_config.lxc, "get_instance", get_instance)
    return get_instance


def test_readonly_config_has_gate_name() -> None:
    assert gate().name == "readonly-config"


def test_check_returns_false_when_device_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_container_lookup(monkeypatch)
    patch_lxc_instance(monkeypatch, {})

    assert not gate().check(microjail())


def test_check_returns_true_when_device_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_container_lookup(monkeypatch)
    patch_lxc_instance(
        monkeypatch,
        {"microjail-config-ro": {"type": "disk", "readonly": "true"}},
    )

    assert gate().check(microjail())


def test_enforce_adds_readonly_disk_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_container_lookup(monkeypatch)
    add_device = Mock()
    monkeypatch.setattr(readonly_config.lxc, "add_device", add_device)

    gate().enforce(microjail())

    add_device.assert_called_once_with(
        CONTAINER_NAME,
        "microjail-config-ro",
        {
            "type": "disk",
            "source": str(microjail().config_path),
            "path": "/project/.microjail/config.yaml",
            "readonly": "true",
        },
        project=LXD_PROJECT,
    )


def test_release_removes_device_after_enforce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_container_lookup(monkeypatch)
    monkeypatch.setattr(readonly_config.lxc, "add_device", Mock())
    remove_device = Mock()
    monkeypatch.setattr(readonly_config.lxc, "remove_device", remove_device)

    ro_gate = gate()
    context = microjail()

    ro_gate.enforce(context)
    ro_gate.release(context)

    remove_device.assert_called_once_with(
        CONTAINER_NAME,
        "microjail-config-ro",
        project=LXD_PROJECT,
    )


def test_release_is_noop_when_not_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remove_device = Mock()
    monkeypatch.setattr(readonly_config.lxc, "remove_device", remove_device)

    gate().release(microjail())

    remove_device.assert_not_called()


def test_enforce_fails_if_workshop_container_is_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_container = Mock(return_value=None)
    monkeypatch.setattr(readonly_config.workshop, "get_container", get_container)

    with pytest.raises(workshop.WorkshopNotLaunchedError) as exc_info:
        gate().enforce(microjail())

    assert exc_info.value.name == WORKSHOP_NAME
    assert exc_info.value.project == PROJECT


def test_check_returns_false_when_container_is_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_container = Mock(return_value=None)
    monkeypatch.setattr(readonly_config.workshop, "get_container", get_container)

    assert not gate().check(microjail())
