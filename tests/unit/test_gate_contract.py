import subprocess
from collections.abc import Callable  # noqa: TC003
from types import SimpleNamespace
from typing import NamedTuple
from unittest.mock import Mock

import pytest

from microjail.gates.base import Gate  # noqa: TC001
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.microjail import MicroJail


def setup_network_drop_unsatisfied(mj: Mock) -> None:
    """Configure mock MicroJail so NetworkDrop.check() returns False."""
    mj.exec_.return_value = subprocess.CompletedProcess(args=[], returncode=0)
    mj.lxc_instance.return_value = SimpleNamespace(devices={"eth0": {"type": "nic"}})


def setup_network_drop_satisfied(mj: Mock) -> None:
    """Configure mock MicroJail so NetworkDrop.check() returns True."""
    mj.exec_.return_value = subprocess.CompletedProcess(args=[], returncode=1)


def setup_readonly_config_unsatisfied(mj: Mock) -> None:
    """Configure mock MicroJail so ReadonlyConfig.check() returns False."""
    mj.lxc_instance.return_value = SimpleNamespace(devices={})
    mj.config_path = "/project/.microjail/config.yaml"


def setup_readonly_config_satisfied(mj: Mock) -> None:
    """Configure mock MicroJail so ReadonlyConfig.check() returns True."""
    mj.lxc_instance.return_value = SimpleNamespace(
        devices={"microjail-config-ro": {"type": "disk", "readonly": "true"}}
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
    return Mock(spec=MicroJail)


def test_enforce_transitions_to_satisfied(spec: GateSpec, mk_mj: Mock) -> None:
    spec.setup_unsatisfied(mk_mj)

    assert not spec.gate.check(mk_mj)
    spec.gate.enforce(mk_mj)
    spec.setup_satisfied(mk_mj)

    assert spec.gate.check(mk_mj)


def test_release_transitions_back_to_unsatisfied(spec: GateSpec, mk_mj: Mock) -> None:
    spec.setup_unsatisfied(mk_mj)
    spec.gate.enforce(mk_mj)
    spec.setup_satisfied(mk_mj)

    assert spec.gate.check(mk_mj)
    spec.gate.release(mk_mj)
    spec.setup_unsatisfied(mk_mj)

    assert not spec.gate.check(mk_mj)


def test_release_before_enforce_is_safe(spec: GateSpec, mk_mj: Mock) -> None:
    spec.gate.release(mk_mj)


def test_release_after_release_is_safe(spec: GateSpec, mk_mj: Mock) -> None:
    spec.setup_unsatisfied(mk_mj)
    spec.gate.enforce(mk_mj)

    spec.gate.release(mk_mj)
    spec.gate.release(mk_mj)
