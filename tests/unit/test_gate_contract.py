import subprocess
from collections.abc import Callable  # noqa: TC003
from types import SimpleNamespace
from typing import NamedTuple
from unittest.mock import AsyncMock, Mock

import pytest

from microjail.gates.base import Gate  # noqa: TC001
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.microjail import MicroJail


def setup_network_drop_unsatisfied(mj: Mock) -> None:
    """Configure mock MicroJail so NetworkDrop.check() returns False."""
    mj.exec_ = AsyncMock(
        return_value=subprocess.CompletedProcess(args=[], returncode=0)
    )
    mj.lxc_instance = AsyncMock(
        return_value=SimpleNamespace(devices={"eth0": {"type": "nic"}})
    )


def setup_network_drop_satisfied(mj: Mock) -> None:
    """Configure mock MicroJail so NetworkDrop.check() returns True."""
    mj.exec_ = AsyncMock(
        return_value=subprocess.CompletedProcess(args=[], returncode=1)
    )


def setup_readonly_config_unsatisfied(mj: Mock) -> None:
    """Configure mock MicroJail so ReadonlyConfig.check() returns False."""
    mj.lxc_instance = AsyncMock(return_value=SimpleNamespace(devices={}))
    mj.config_path = "/project/.microjail/config.yaml"


def setup_readonly_config_satisfied(mj: Mock) -> None:
    """Configure mock MicroJail so ReadonlyConfig.check() returns True."""
    mj.lxc_instance = AsyncMock(
        return_value=SimpleNamespace(
            devices={"microjail-config-ro": {"type": "disk", "readonly": "true"}}
        )
    )
    mj.config_path = "/project/.microjail/config.yaml"


class GateSpec(NamedTuple):
    gate: Gate
    setup_unsatisfied: Callable[[Mock], None]
    setup_satisfied: Callable[[Mock], None]


@pytest.fixture(
    params=[
        pytest.param(
            GateSpec(
                gate=NetworkDrop(),
                setup_unsatisfied=setup_network_drop_unsatisfied,
                setup_satisfied=setup_network_drop_satisfied,
            ),
            id="NetworkDrop",
        ),
        pytest.param(
            GateSpec(
                gate=ReadonlyConfig(),
                setup_unsatisfied=setup_readonly_config_unsatisfied,
                setup_satisfied=setup_readonly_config_satisfied,
            ),
            id="ReadonlyConfig",
        ),
    ]
)
def spec(request: pytest.FixtureRequest) -> GateSpec:
    return request.param


@pytest.fixture
def mk_mj() -> Mock:
    mj = Mock(spec=MicroJail)
    mj.lxc_instance = AsyncMock(return_value=SimpleNamespace(devices={}))
    mj.profile_devices = AsyncMock()
    mj.remove_device = AsyncMock()
    mj.add_device = AsyncMock()
    mj.restore_workshop = AsyncMock()
    mj.container_name = AsyncMock()
    mj.exec_ = AsyncMock()
    return mj


async def test_enforce_transitions_to_satisfied(spec: GateSpec, mk_mj: Mock) -> None:
    spec.setup_unsatisfied(mk_mj)

    assert not await spec.gate.check(mk_mj)
    await spec.gate.enforce(mk_mj)
    spec.setup_satisfied(mk_mj)

    assert await spec.gate.check(mk_mj)


async def test_release_transitions_back_to_unsatisfied(
    spec: GateSpec, mk_mj: Mock
) -> None:
    spec.setup_unsatisfied(mk_mj)
    await spec.gate.enforce(mk_mj)
    spec.setup_satisfied(mk_mj)

    assert await spec.gate.check(mk_mj)
    await spec.gate.release(mk_mj)
    spec.setup_unsatisfied(mk_mj)

    assert not await spec.gate.check(mk_mj)


async def test_release_before_enforce_is_safe(spec: GateSpec, mk_mj: Mock) -> None:
    await spec.gate.release(mk_mj)


async def test_release_after_release_is_safe(spec: GateSpec, mk_mj: Mock) -> None:
    spec.setup_unsatisfied(mk_mj)
    await spec.gate.enforce(mk_mj)

    await spec.gate.release(mk_mj)
    await spec.gate.release(mk_mj)
