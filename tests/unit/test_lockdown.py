from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast
from unittest.mock import Mock, call

import pytest

from microjail.caps.base import Capability
from microjail.gates.base import Gate
from microjail.lockdown import GateError, Lockdown

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# Expected lifecycle call sequences for a cap or gate.
PROVISIONED_THEN_REVOKED = (call.check(), call.provide(), call.check(), call.revoke())
ENFORCED_THEN_RELEASED = (call.check(), call.enforce(), call.check(), call.release())
CHECKED_ONLY = (call.check(),)


class CapabilityMock(Capability, Protocol):
    mock_calls: list[object]


class GateMock(Gate, Protocol):
    mock_calls: list[object]


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    checks: Sequence[bool] | None
    expected_calls: tuple[object, ...]


@pytest.fixture
def capability_factory() -> Callable[[ComponentSpec], CapabilityMock]:
    """Build a spec-constrained capability mock from a component spec."""

    def build(spec: ComponentSpec) -> CapabilityMock:
        cap = Mock(spec=Capability)
        cap.name = spec.name
        if spec.checks is not None:
            cap.check.side_effect = spec.checks
        return cast("CapabilityMock", cap)

    return build


@pytest.fixture
def gate_factory() -> Callable[[ComponentSpec], GateMock]:
    """Build a spec-constrained gate mock from a component spec."""

    def build(spec: ComponentSpec) -> GateMock:
        gate = Mock(spec=Gate)
        gate.name = spec.name
        if spec.checks is not None:
            gate.check.side_effect = spec.checks
        return cast("GateMock", gate)

    return build


def lockdown_from_specs(
    cap_specs: Sequence[ComponentSpec],
    gate_specs: Sequence[ComponentSpec],
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> tuple[Lockdown, list[CapabilityMock], list[GateMock]]:
    cap_mocks = [capability_factory(spec) for spec in cap_specs]
    gate_mocks = [gate_factory(spec) for spec in gate_specs]
    return Lockdown(caps=[*cap_mocks], gates=[*gate_mocks]), cap_mocks, gate_mocks


def assert_mock_calls(
    mocks: Sequence[CapabilityMock] | Sequence[GateMock],
    specs: Sequence[ComponentSpec],
) -> None:
    for mock, spec in zip(mocks, specs, strict=True):
        assert mock.mock_calls == list(spec.expected_calls)


def test_ensure_releases_applied_state_if_gate_verification_fails(
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> None:
    cap_specs = [ComponentSpec("proxy", [False, True], PROVISIONED_THEN_REVOKED)]
    gate_specs = [
        ComponentSpec("network", [False, True], ENFORCED_THEN_RELEASED),
        ComponentSpec("secrets", [False, False], ENFORCED_THEN_RELEASED),
    ]
    lockdown, cap_mocks, gate_mocks = lockdown_from_specs(
        cap_specs=cap_specs,
        gate_specs=gate_specs,
        capability_factory=capability_factory,
        gate_factory=gate_factory,
    )

    with pytest.raises(GateError):
        lockdown.ensure()

    assert_mock_calls(cap_mocks, cap_specs)
    assert_mock_calls(gate_mocks, gate_specs)


def test_ensure_preserves_preexisting_state_if_later_gate_fails(
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> None:
    cap_specs = [ComponentSpec("proxy", [True], CHECKED_ONLY)]
    gate_specs = [
        ComponentSpec("network", [True], CHECKED_ONLY),
        ComponentSpec("secrets", [False, False], ENFORCED_THEN_RELEASED),
    ]
    lockdown, cap_mocks, gate_mocks = lockdown_from_specs(
        cap_specs=cap_specs,
        gate_specs=gate_specs,
        capability_factory=capability_factory,
        gate_factory=gate_factory,
    )

    with pytest.raises(GateError):
        lockdown.ensure()

    assert_mock_calls(cap_mocks, cap_specs)
    assert_mock_calls(gate_mocks, gate_specs)


def test_ensure_aborts_remaining_gates_after_first_failure(
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> None:
    cap_specs: list[ComponentSpec] = []
    gate_specs = [
        ComponentSpec("secrets", [False, False], ENFORCED_THEN_RELEASED),
        ComponentSpec("network", None, ()),
    ]
    lockdown, cap_mocks, gate_mocks = lockdown_from_specs(
        cap_specs=cap_specs,
        gate_specs=gate_specs,
        capability_factory=capability_factory,
        gate_factory=gate_factory,
    )

    with pytest.raises(GateError):
        lockdown.ensure()

    assert_mock_calls(cap_mocks, cap_specs)
    assert_mock_calls(gate_mocks, gate_specs)
