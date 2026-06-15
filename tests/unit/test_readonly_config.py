from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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


async def test_check_returns_false_when_device_absent() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance = AsyncMock(return_value=SimpleNamespace(devices={}))

    assert not await gate().check(mock_mj)


async def test_check_returns_true_when_device_present() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance = AsyncMock(
        return_value=SimpleNamespace(
            devices={"microjail-config-ro": {"type": "disk", "readonly": "true"}}
        )
    )

    assert await gate().check(mock_mj)


async def test_enforce_adds_readonly_disk_device() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.config_path = "/project/.microjail/config.yaml"
    mock_mj.add_device = AsyncMock()

    await gate().enforce(mock_mj)

    mock_mj.add_device.assert_called_once_with(
        "microjail-config-ro",
        {
            "type": "disk",
            "source": "/project/.microjail/config.yaml",
            "path": CONTAINER_CONFIG_PATH,
            "readonly": "true",
        },
    )


async def test_release_removes_device_after_enforce(monkeypatch) -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.config_path = "/project/.microjail/config.yaml"
    mock_mj.add_device = AsyncMock()
    mock_mj.remove_device = AsyncMock()
    # check() will be called in release, so we also need to mock lxc_instance (which check calls)
    mock_mj.lxc_instance = AsyncMock(return_value=SimpleNamespace(devices={}))

    ro_gate = gate()
    await ro_gate.enforce(mock_mj)
    await ro_gate.release(mock_mj)

    mock_mj.remove_device.assert_called_once_with("microjail-config-ro")


async def test_release_is_noop_when_not_enforced() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance = AsyncMock(return_value=SimpleNamespace(devices={}))
    mock_mj.remove_device = AsyncMock()

    await gate().release(mock_mj)

    mock_mj.remove_device.assert_not_called()


async def test_enforce_fails_if_workshop_container_is_not_available() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.config_path = "/project/.microjail/config.yaml"
    mock_mj.add_device = AsyncMock(
        side_effect=WorkshopNotLaunchedError(
            name=WORKSHOP_NAME,
            project=PROJECT,
        )
    )

    with pytest.raises(WorkshopNotLaunchedError) as exc_info:
        await gate().enforce(mock_mj)

    assert exc_info.value.name == WORKSHOP_NAME
    assert exc_info.value.project == PROJECT


async def test_check_returns_false_when_container_is_not_available() -> None:
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lxc_instance = AsyncMock(
        side_effect=WorkshopNotLaunchedError(
            name=WORKSHOP_NAME,
            project=PROJECT,
        )
    )

    assert not await gate().check(mock_mj)
