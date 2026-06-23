from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from microjail.adapters.workshop import WorkshopNotLaunchedError
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.microjail import MicroJail

WORKSHOP_NAME = "mj-workshop"
PROJECT = Path("/project")
CONTAINER_CONFIG_PATH = "/project/.microjail/config.yaml"


def gate() -> ReadonlyConfig:
    return ReadonlyConfig()


def test_readonly_config_has_gate_name() -> None:
    assert gate().name == "readonly-config"


def test_check_returns_false_when_device_absent() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.return_value = SimpleNamespace(devices={})

    assert not gate().check(mock_mj)


def test_check_returns_true_when_device_present() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.return_value = SimpleNamespace(
        devices={"microjail-config-ro": {"type": "disk", "readonly": "true"}}
    )

    assert gate().check(mock_mj)


def test_enforce_adds_readonly_disk_device() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.config_path = "/project/.microjail/config.yaml"

    gate().enforce(mock_mj)

    mock_mj.add_device.assert_called_once_with(
        "microjail-config-ro",
        {
            "type": "disk",
            "source": "/project/.microjail/config.yaml",
            "path": CONTAINER_CONFIG_PATH,
            "readonly": "true",
        },
    )


def test_release_removes_device_after_enforce() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.config_path = "/project/.microjail/config.yaml"

    ro_gate = gate()
    ro_gate.enforce(mock_mj)
    ro_gate.release(mock_mj)

    mock_mj.remove_device.assert_called_once_with("microjail-config-ro")


def test_release_is_noop_when_not_enforced() -> None:
    mock_mj = Mock(spec=MicroJail)

    gate().release(mock_mj)

    mock_mj.remove_device.assert_not_called()


def test_enforce_fails_if_workshop_container_is_not_available() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.config_path = "/project/.microjail/config.yaml"
    mock_mj.add_device.side_effect = WorkshopNotLaunchedError(
        name=WORKSHOP_NAME,
        project=PROJECT,
    )

    with pytest.raises(WorkshopNotLaunchedError) as exc_info:
        gate().enforce(mock_mj)

    assert exc_info.value.name == WORKSHOP_NAME
    assert exc_info.value.project == PROJECT


def test_check_returns_false_when_container_is_not_available() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance.side_effect = WorkshopNotLaunchedError(
        name=WORKSHOP_NAME,
        project=PROJECT,
    )

    assert not gate().check(mock_mj)


def test_readonly_config_verify() -> None:
    mock_mj = Mock(spec=MicroJail)
    assert gate().verify(mock_mj) is True
