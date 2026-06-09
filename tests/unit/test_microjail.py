from typing import TYPE_CHECKING, Literal, Protocol
from unittest.mock import Mock, call

import pytest

from microjail.adapters import workshop
from microjail.caps.base import Capability
from microjail.gates.base import Gate
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import CapabilityError, GateError, Lockdown
from microjail.microjail import (
    ConfigNotFoundError,
    MicroJail,
    WorkshopNotReadyError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class CapabilityMock(Capability, Protocol):
    mock_calls: list[object]


class GateMock(Gate, Protocol):
    mock_calls: list[object]


@pytest.fixture
def tmp_microjail(tmp_path: Path, project_name: str) -> MicroJail:
    return MicroJail(
        name=project_name,
        project_path=tmp_path,
        lockdown=Lockdown(caps=[], gates=[]),
    )


def expected_calls(method_names: Sequence[str], microjail: MicroJail) -> list[object]:
    return [getattr(call, method_name)(microjail) for method_name in method_names]


def assert_calls(
    mocks: Sequence[CapabilityMock | GateMock],
    method_names: Sequence[str],
    microjail: MicroJail,
) -> None:
    assert mocks[0].mock_calls == expected_calls(method_names, microjail)


def mark_workshop_ready(monkeypatch: pytest.MonkeyPatch, microjail: MicroJail) -> None:
    monkeypatch.setattr(
        MicroJail,
        "workshop_info",
        Mock(return_value=workshop.WorkshopInfo(name=microjail.name, status="ready")),
    )


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


def test_load_round_trips_default_gates(tmp_path: Path, project_name: str) -> None:
    microjail = MicroJail(
        name=project_name,
        project_path=tmp_path,
        lockdown=Lockdown.default(),
    )
    microjail.save()

    loaded = MicroJail.load(tmp_path)
    assert loaded.name == microjail.name
    assert loaded.project_path == microjail.project_path
    assert isinstance(loaded.lockdown.gates[0], NetworkDrop)
    assert isinstance(loaded.lockdown.gates[1], ReadonlyConfig)


def test_load_raises_when_config_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError) as exc_info:
        MicroJail.load(tmp_path)

    assert exc_info.value.project_path == tmp_path


def test_ensure_fails_without_running_policy_if_workshop_is_not_launched(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    capability = Mock(spec=Capability)
    capability.name = "proxy"
    capability.check.return_value = False
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.return_value = False
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[capability], gates=[gate]),
    )
    monkeypatch.setattr(MicroJail, "workshop_info", Mock(return_value=None))

    with pytest.raises(workshop.WorkshopNotLaunchedError):
        microjail.ensure()

    assert capability.mock_calls == []
    assert gate.mock_calls == []


@pytest.mark.parametrize("status", ["pending", "stopped"])
def test_ensure_fails_without_running_policy_if_workshop_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_microjail: MicroJail,
    status: Literal["pending", "stopped"],
) -> None:
    capability = Mock(spec=Capability)
    capability.name = "proxy"
    capability.check.return_value = False
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.return_value = False
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[capability], gates=[gate]),
    )
    monkeypatch.setattr(
        MicroJail,
        "workshop_info",
        Mock(return_value=workshop.WorkshopInfo(name=microjail.name, status=status)),
    )

    with pytest.raises(WorkshopNotReadyError):
        microjail.ensure()

    assert capability.mock_calls == []
    assert gate.mock_calls == []


def test_ensure_provisions_capabilities_before_enforcing_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
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
    mark_workshop_ready(monkeypatch, microjail)

    microjail.ensure()

    # Capability was provisioned before gate was enforced.
    assert capability.mock_calls == [
        call.check(microjail),
        call.provide(microjail),
        call.check(microjail),
    ]
    assert gate.mock_calls == [
        call.check(microjail),
        call.enforce(microjail),
        call.check(microjail),
    ]


def test_ensure_skips_satisfied_capabilities_and_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.return_value = True
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.return_value = True
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    microjail.ensure()

    assert_calls([cap], ("check",), microjail)
    assert_calls([gate], ("check",), microjail)


def test_ensure_releases_applied_state_if_capability_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.side_effect = [False, False]
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[cap], gates=[]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    with pytest.raises(CapabilityError):
        microjail.ensure()

    assert_calls([cap], ("check", "provide", "check", "revoke"), microjail)


def test_ensure_releases_applied_state_if_gate_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.side_effect = [False, True]
    gate_a = Mock(spec=Gate)
    gate_a.name = "network"
    gate_a.check.side_effect = [False, True]
    gate_b = Mock(spec=Gate)
    gate_b.name = "secrets"
    gate_b.check.side_effect = [False, False]
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[cap], gates=[gate_a, gate_b]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    with pytest.raises(GateError):
        microjail.ensure()

    assert_calls([cap], ("check", "provide", "check", "revoke"), microjail)
    assert gate_a.mock_calls == expected_calls(
        ("check", "enforce", "check", "release"), microjail
    )
    assert gate_b.mock_calls == expected_calls(
        ("check", "enforce", "check", "release"), microjail
    )


def test_ensure_preserves_preexisting_state_if_later_gate_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.return_value = True
    gate_a = Mock(spec=Gate)
    gate_a.name = "network"
    gate_a.check.return_value = True
    gate_b = Mock(spec=Gate)
    gate_b.name = "secrets"
    gate_b.check.side_effect = [False, False]
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[cap], gates=[gate_a, gate_b]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    with pytest.raises(GateError):
        microjail.ensure()

    assert_calls([cap], ("check",), microjail)
    assert_calls([gate_a], ("check",), microjail)
    assert gate_b.mock_calls == expected_calls(
        ("check", "enforce", "check", "release"), microjail
    )


def test_ensure_aborts_remaining_gates_after_first_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    gate_a = Mock(spec=Gate)
    gate_a.name = "secrets"
    gate_a.check.side_effect = [False, False]
    gate_b = Mock(spec=Gate)
    gate_b.name = "network"
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[], gates=[gate_a, gate_b]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    with pytest.raises(GateError):
        microjail.ensure()

    assert gate_a.mock_calls == expected_calls(
        ("check", "enforce", "check", "release"), microjail
    )
    assert gate_b.mock_calls == []


def test_default_lockdown_ensure_enforces_network_drop(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    net = Mock(spec=Gate)
    net.name = "network-egress"
    net.check.side_effect = [False, True]
    ro = Mock(spec=Gate)
    ro.name = "readonly-config"
    ro.check.return_value = True
    microjail = MicroJail(
        name=tmp_microjail.name,
        project_path=tmp_microjail.project_path,
        lockdown=Lockdown(caps=[], gates=[net, ro]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    microjail.ensure()

    assert net.mock_calls == expected_calls(("check", "enforce", "check"), microjail)
    assert_calls([ro], ("check",), microjail)
