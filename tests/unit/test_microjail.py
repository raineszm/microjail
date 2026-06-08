from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast
from unittest.mock import Mock, call

import pytest

from microjail.caps.base import Capability
from microjail.gates.base import Gate
from microjail.gates.network_drop import NetworkDrop
from microjail.lockdown import CapabilityError, GateError, Lockdown
from microjail.microjail import (
    ConfigNotFoundError,
    MicroJail,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path


class CapabilityMock(Capability, Protocol):
    mock_calls: list[object]


class GateMock(Gate, Protocol):
    mock_calls: list[object]


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    checks: Sequence[bool] | None
    expected_methods: tuple[str, ...]


@pytest.fixture
def tmp_microjail(tmp_path: Path, project_name: str) -> MicroJail:
    return MicroJail(
        name=project_name,
        project_path=tmp_path,
        lockdown=Lockdown(caps=[], gates=[]),
    )


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


def microjail_from_specs(
    tmp_microjail: MicroJail,
    cap_specs: Sequence[ComponentSpec],
    gate_specs: Sequence[ComponentSpec],
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> tuple[MicroJail, list[CapabilityMock], list[GateMock]]:
    cap_mocks = [capability_factory(spec) for spec in cap_specs]
    gate_mocks = [gate_factory(spec) for spec in gate_specs]
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[*cap_mocks], gates=[*gate_mocks]),
    )
    return microjail, cap_mocks, gate_mocks


def expected_calls(method_names: Sequence[str], microjail: MicroJail) -> list[object]:
    return [getattr(call, method_name)(microjail) for method_name in method_names]


def assert_mock_calls(
    mocks: Sequence[CapabilityMock] | Sequence[GateMock],
    specs: Sequence[ComponentSpec],
    microjail: MicroJail,
) -> None:
    for mock, spec in zip(mocks, specs, strict=True):
        assert mock.mock_calls == expected_calls(spec.expected_methods, microjail)


def test_save_writes_config_under_microjail_dir(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()
    assert tmp_microjail.config_path.exists()


def test_save_creates_missing_microjail_dir(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()

    assert tmp_microjail.config_dir.is_dir()


def test_load_round_trips_saved_config(tmp_microjail: MicroJail) -> None:
    tmp_microjail.save()

    loaded = MicroJail.load(tmp_microjail.project_path)

    assert loaded == tmp_microjail


def test_load_round_trips_default_network_drop_gate(
    tmp_path: Path, project_name: str
) -> None:
    microjail = MicroJail(
        name=project_name,
        project_path=tmp_path,
        lockdown=Lockdown.default(),
    )
    microjail.save()

    loaded = MicroJail.load(tmp_path)

    assert len(loaded.lockdown.gates) == 1
    assert isinstance(loaded.lockdown.gates[0], NetworkDrop)


def test_load_raises_when_config_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError) as exc_info:
        MicroJail.load(tmp_path)

    assert exc_info.value.project_path == tmp_path


def test_ensure_provisions_capabilities_before_enforcing_gates(
    tmp_microjail: MicroJail,
) -> None:
    capability = Mock(spec=Capability)
    capability.name = "proxy"
    capability.check.side_effect = [False, True]
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.side_effect = [False, True]
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[capability], gates=[gate]),
    )
    calls = Mock()
    calls.attach_mock(capability, "capability")
    calls.attach_mock(gate, "gate")

    microjail.ensure()

    assert calls.mock_calls == [
        call.capability.check(microjail),
        call.capability.provide(microjail),
        call.capability.check(microjail),
        call.gate.check(microjail),
        call.gate.enforce(microjail),
        call.gate.check(microjail),
    ]


def test_ensure_skips_satisfied_capabilities_and_gates(
    tmp_microjail: MicroJail,
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> None:
    cap_specs = [ComponentSpec("proxy", [True], ("check",))]
    gate_specs = [ComponentSpec("network", [True], ("check",))]
    microjail, cap_mocks, gate_mocks = microjail_from_specs(
        tmp_microjail=tmp_microjail,
        cap_specs=cap_specs,
        gate_specs=gate_specs,
        capability_factory=capability_factory,
        gate_factory=gate_factory,
    )

    microjail.ensure()

    assert_mock_calls(cap_mocks, cap_specs, microjail)
    assert_mock_calls(gate_mocks, gate_specs, microjail)


def test_ensure_releases_applied_state_if_capability_verification_fails(
    tmp_microjail: MicroJail,
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> None:
    cap_specs = [
        ComponentSpec("proxy", [False, False], ("check", "provide", "check", "revoke"))
    ]
    gate_specs = [ComponentSpec("network", None, ())]
    microjail, cap_mocks, gate_mocks = microjail_from_specs(
        tmp_microjail=tmp_microjail,
        cap_specs=cap_specs,
        gate_specs=gate_specs,
        capability_factory=capability_factory,
        gate_factory=gate_factory,
    )

    with pytest.raises(CapabilityError):
        microjail.ensure()

    assert_mock_calls(cap_mocks, cap_specs, microjail)
    assert_mock_calls(gate_mocks, gate_specs, microjail)


def test_ensure_releases_applied_state_if_gate_verification_fails(
    tmp_microjail: MicroJail,
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> None:
    cap_specs = [
        ComponentSpec("proxy", [False, True], ("check", "provide", "check", "revoke"))
    ]
    gate_specs = [
        ComponentSpec(
            "network", [False, True], ("check", "enforce", "check", "release")
        ),
        ComponentSpec(
            "secrets", [False, False], ("check", "enforce", "check", "release")
        ),
    ]
    microjail, cap_mocks, gate_mocks = microjail_from_specs(
        tmp_microjail=tmp_microjail,
        cap_specs=cap_specs,
        gate_specs=gate_specs,
        capability_factory=capability_factory,
        gate_factory=gate_factory,
    )

    with pytest.raises(GateError):
        microjail.ensure()

    assert_mock_calls(cap_mocks, cap_specs, microjail)
    assert_mock_calls(gate_mocks, gate_specs, microjail)


def test_ensure_preserves_preexisting_state_if_later_gate_fails(
    tmp_microjail: MicroJail,
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> None:
    cap_specs = [ComponentSpec("proxy", [True], ("check",))]
    gate_specs = [
        ComponentSpec("network", [True], ("check",)),
        ComponentSpec(
            "secrets", [False, False], ("check", "enforce", "check", "release")
        ),
    ]
    microjail, cap_mocks, gate_mocks = microjail_from_specs(
        tmp_microjail=tmp_microjail,
        cap_specs=cap_specs,
        gate_specs=gate_specs,
        capability_factory=capability_factory,
        gate_factory=gate_factory,
    )

    with pytest.raises(GateError):
        microjail.ensure()

    assert_mock_calls(cap_mocks, cap_specs, microjail)
    assert_mock_calls(gate_mocks, gate_specs, microjail)


def test_ensure_aborts_remaining_gates_after_first_failure(
    tmp_microjail: MicroJail,
    capability_factory: Callable[[ComponentSpec], CapabilityMock],
    gate_factory: Callable[[ComponentSpec], GateMock],
) -> None:
    cap_specs: list[ComponentSpec] = []
    gate_specs = [
        ComponentSpec(
            "secrets", [False, False], ("check", "enforce", "check", "release")
        ),
        ComponentSpec("network", None, ()),
    ]
    microjail, cap_mocks, gate_mocks = microjail_from_specs(
        tmp_microjail=tmp_microjail,
        cap_specs=cap_specs,
        gate_specs=gate_specs,
        capability_factory=capability_factory,
        gate_factory=gate_factory,
    )

    with pytest.raises(GateError):
        microjail.ensure()

    assert_mock_calls(cap_mocks, cap_specs, microjail)
    assert_mock_calls(gate_mocks, gate_specs, microjail)


def test_default_lockdown_ensure_enforces_network_drop(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    check = Mock(side_effect=[False, True])
    enforce = Mock()
    monkeypatch.setattr(NetworkDrop, "check", check)
    monkeypatch.setattr(NetworkDrop, "enforce", enforce)
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown.default(),
    )

    microjail.ensure()

    assert check.mock_calls == [call(microjail), call(microjail)]
    enforce.assert_called_once_with(microjail)
