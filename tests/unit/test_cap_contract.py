from typing import TYPE_CHECKING, NamedTuple
from unittest.mock import AsyncMock, Mock

import pytest

from microjail.adapters import workshop
from microjail.caps.base import Capability  # noqa: TC001
from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from collections.abc import Callable


class TestCapability:
    """Minimal capability used only by the contract harness.

    Delegates state to mock MicroJail attributes so setup functions
    can control check() results without side effects.
    """

    name = "test-cap"
    fatal = False

    async def check(self, microjail: MicroJail) -> bool:
        return getattr(microjail, "cap_is_satisfied", False)

    async def provide(self, microjail: MicroJail) -> None:
        setattr(microjail, "cap_provide_called", True)  # noqa: B010

    async def revoke(self, microjail: MicroJail) -> None:
        setattr(microjail, "cap_revoke_called", True)  # noqa: B010


def setup_test_cap_unsatisfied(mj: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    del monkeypatch
    mj.cap_is_satisfied = False


def setup_test_cap_satisfied(mj: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    del monkeypatch
    mj.cap_is_satisfied = True


def setup_endpoint_unsatisfied(mj: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    mj.name = "mj-workshop"
    mj.project_path = object()
    monkeypatch.setattr(workshop, "connections", AsyncMock(return_value=[]))
    monkeypatch.setattr(workshop, "endpoint_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr(workshop, "add_tunnel_plug", Mock())
    monkeypatch.setattr(workshop, "add_tunnel_slot", Mock())
    monkeypatch.setattr(workshop, "refresh", AsyncMock())
    monkeypatch.setattr(workshop, "connect", AsyncMock())
    monkeypatch.setattr(workshop, "disconnect", AsyncMock())
    monkeypatch.setattr(workshop, "remove_tunnel_plug", Mock(return_value=True))
    monkeypatch.setattr(workshop, "remove_tunnel_slot", Mock())


def setup_endpoint_satisfied(mj: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    mj.name = "mj-workshop"
    mj.project_path = object()
    monkeypatch.setattr(
        workshop,
        "connections",
        AsyncMock(
            return_value=[
                ("mj-workshop/microjail:inference", "mj-workshop/system:inference")
            ]
        ),
    )
    monkeypatch.setattr(workshop, "endpoint_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr(workshop, "add_tunnel_plug", Mock())
    monkeypatch.setattr(workshop, "add_tunnel_slot", Mock())
    monkeypatch.setattr(workshop, "refresh", AsyncMock())
    monkeypatch.setattr(workshop, "connect", AsyncMock())
    monkeypatch.setattr(workshop, "disconnect", AsyncMock())
    monkeypatch.setattr(workshop, "remove_tunnel_plug", Mock(return_value=False))
    monkeypatch.setattr(workshop, "remove_tunnel_slot", Mock())


class CapSpec(NamedTuple):
    cap: Capability
    setup_unsatisfied: Callable[[Mock, pytest.MonkeyPatch], None]
    setup_satisfied: Callable[[Mock, pytest.MonkeyPatch], None]


@pytest.fixture(
    params=[
        pytest.param(
            CapSpec(
                cap=TestCapability(),
                setup_unsatisfied=setup_test_cap_unsatisfied,
                setup_satisfied=setup_test_cap_satisfied,
            ),
            id="TestCapability",
        ),
        pytest.param(
            CapSpec(
                cap=WorkshopEndpointCapability(
                    name="inference", host_endpoint="127.0.0.1:8080"
                ),
                setup_unsatisfied=setup_endpoint_unsatisfied,
                setup_satisfied=setup_endpoint_satisfied,
            ),
            id="WorkshopEndpointCapability",
        ),
    ]
)
def spec(request: pytest.FixtureRequest) -> CapSpec:
    return request.param


@pytest.fixture
def mk_mj() -> Mock:
    return Mock(spec=MicroJail)


async def test_provide_transitions_to_satisfied(
    spec: CapSpec, mk_mj: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec.setup_unsatisfied(mk_mj, monkeypatch)

    assert not await spec.cap.check(mk_mj)
    await spec.cap.provide(mk_mj)
    spec.setup_satisfied(mk_mj, monkeypatch)

    assert await spec.cap.check(mk_mj)


async def test_revoke_transitions_back_to_unsatisfied(
    spec: CapSpec, mk_mj: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec.setup_unsatisfied(mk_mj, monkeypatch)
    await spec.cap.provide(mk_mj)
    spec.setup_satisfied(mk_mj, monkeypatch)

    assert await spec.cap.check(mk_mj)
    await spec.cap.revoke(mk_mj)
    spec.setup_unsatisfied(mk_mj, monkeypatch)

    assert not await spec.cap.check(mk_mj)


async def test_revoke_before_provide_is_safe(
    spec: CapSpec, mk_mj: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec.setup_unsatisfied(mk_mj, monkeypatch)

    await spec.cap.revoke(mk_mj)


async def test_revoke_after_revoke_is_safe(
    spec: CapSpec, mk_mj: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec.setup_unsatisfied(mk_mj, monkeypatch)
    await spec.cap.provide(mk_mj)

    await spec.cap.revoke(mk_mj)
    await spec.cap.revoke(mk_mj)
