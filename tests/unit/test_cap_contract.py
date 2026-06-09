from typing import NamedTuple
from unittest.mock import Mock

import pytest

from microjail.caps.base import Capability  # noqa: TC001
from microjail.microjail import MicroJail


class TestCapability:
    """Minimal capability used only by the contract harness.

    Delegates state to mock MicroJail attributes so setup functions
    can control check() results without side effects.
    """

    name = "test-cap"

    def check(self, microjail: MicroJail) -> bool:
        return microjail.cap_is_satisfied

    def provide(self, microjail: MicroJail) -> None:
        microjail.cap_provide_called = True

    def revoke(self, microjail: MicroJail) -> None:
        microjail.cap_revoke_called = True


def setup_test_cap_unsatisfied(mj: Mock) -> None:
    mj.cap_is_satisfied = False


def setup_test_cap_satisfied(mj: Mock) -> None:
    mj.cap_is_satisfied = True


class CapSpec(NamedTuple):
    cap: Capability
    setup_unsatisfied: object
    setup_satisfied: object


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
    ]
)
def spec(request: pytest.FixtureRequest) -> CapSpec:
    return request.param


@pytest.fixture
def mk_mj() -> Mock:
    return Mock(spec=MicroJail)


def test_provide_transitions_to_satisfied(spec: CapSpec, mk_mj: Mock) -> None:
    spec.setup_unsatisfied(mk_mj)

    assert not spec.cap.check(mk_mj)
    spec.cap.provide(mk_mj)
    spec.setup_satisfied(mk_mj)

    assert spec.cap.check(mk_mj)


def test_revoke_transitions_back_to_unsatisfied(spec: CapSpec, mk_mj: Mock) -> None:
    spec.setup_unsatisfied(mk_mj)
    spec.cap.provide(mk_mj)
    spec.setup_satisfied(mk_mj)

    assert spec.cap.check(mk_mj)
    spec.cap.revoke(mk_mj)
    spec.setup_unsatisfied(mk_mj)

    assert not spec.cap.check(mk_mj)


def test_revoke_before_provide_is_safe(spec: CapSpec, mk_mj: Mock) -> None:
    spec.cap.revoke(mk_mj)


def test_revoke_after_revoke_is_safe(spec: CapSpec, mk_mj: Mock) -> None:
    spec.setup_unsatisfied(mk_mj)
    spec.cap.provide(mk_mj)

    spec.cap.revoke(mk_mj)
    spec.cap.revoke(mk_mj)
