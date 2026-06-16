from typing import TYPE_CHECKING, Literal, Protocol
from unittest.mock import Mock, call

import pytest

from microjail.adapters import workshop
from microjail.adapters.workshop import Workshop
from microjail.caps.base import Capability
from microjail.gates.base import Gate
from microjail.lockdown import CapabilityReleaseError, GateReleaseError, Lockdown
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
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
        workshop=Workshop(name=project_name, project=tmp_path),
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


def test_application_fails_without_running_policy_if_workshop_is_not_launched(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    capability = Mock(spec=Capability)
    capability.name = "proxy"
    capability.check.return_value = False
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.return_value = False
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[capability], gates=[gate]),
    )
    monkeypatch.setattr(MicroJail, "workshop_info", Mock(return_value=None))

    with pytest.raises(workshop.WorkshopNotLaunchedError):
        microjail.ensure(ApplicationIntent.RUN)

    assert capability.mock_calls == []
    assert gate.mock_calls == []


@pytest.mark.parametrize("status", ["pending", "stopped"])
def test_application_fails_without_running_policy_if_workshop_is_not_ready(
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
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[capability], gates=[gate]),
    )
    monkeypatch.setattr(
        MicroJail,
        "workshop_info",
        Mock(return_value=workshop.WorkshopInfo(name=microjail.name, status=status)),
    )

    with pytest.raises(WorkshopNotReadyError):
        microjail.ensure(ApplicationIntent.RUN)

    assert capability.mock_calls == []
    assert gate.mock_calls == []


def test_run_application_provisions_capabilities_before_enforcing_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    capability = Mock(spec=Capability)
    capability.name = "proxy"
    capability.check.side_effect = [False, True]
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.side_effect = [False, True]
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[capability], gates=[gate]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.SUCCESS
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


def test_application_skips_satisfied_capabilities_and_gates(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.return_value = True
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.return_value = True
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.SUCCESS
    assert_calls([cap], ("check",), microjail)
    assert_calls([gate], ("check",), microjail)


def test_run_application_rolls_back_if_capability_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.side_effect = [False, False]
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap], gates=[]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.CAPABILITY_APPLICATION_FAILURE
    assert [error.name for error in result.capability_failures] == ["proxy"]
    assert result.rollback_failures == ()
    assert_calls([cap], ("check", "provide", "check", "revoke"), microjail)


def test_run_application_reports_rollback_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.side_effect = [False, True]
    cap.revoke.side_effect = RuntimeError("still mounted")
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.side_effect = [False, False]
    gate.release.side_effect = RuntimeError("still gated")
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.GATE_APPLICATION_FAILURE
    assert result.gate_failure is not None
    assert result.gate_failure.name == "network"
    assert [type(error) for error in result.rollback_failures] == [
        GateReleaseError,
        CapabilityReleaseError,
    ]
    assert [error.name for error in result.rollback_failures] == ["network", "proxy"]


def test_lock_application_capability_failure_still_attempts_gate_enforcement(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.side_effect = [False, False]
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.side_effect = [False, True]
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.LOCK)

    assert result.status is ApplicationStatus.CAPABILITY_APPLICATION_FAILURE
    assert result.gates_enforced == 1
    assert result.rollback_failures == ()
    assert_calls([cap], ("check", "provide", "check"), microjail)
    assert_calls([gate], ("check", "enforce", "check"), microjail)


def test_lock_application_gate_failure_keeps_capability_failures_as_context(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.side_effect = [False, False]
    gate = Mock(spec=Gate)
    gate.name = "network"
    gate.check.side_effect = [False, False]
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap], gates=[gate]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.LOCK)

    assert result.status is ApplicationStatus.GATE_APPLICATION_FAILURE
    assert result.gate_failure is not None
    assert result.gate_failure.name == "network"
    assert [error.name for error in result.capability_failures] == ["proxy"]
    assert result.rollback_failures == ()
    assert_calls([cap], ("check", "provide", "check"), microjail)
    assert_calls([gate], ("check", "enforce", "check"), microjail)


def test_run_application_preserves_preexisting_state_if_later_gate_fails(
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
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap], gates=[gate_a, gate_b]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.GATE_APPLICATION_FAILURE
    assert_calls([cap], ("check",), microjail)
    assert_calls([gate_a], ("check",), microjail)
    assert gate_b.mock_calls == expected_calls(
        ("check", "enforce", "check", "release"), microjail
    )


def test_run_application_aborts_remaining_gates_after_first_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    gate_a = Mock(spec=Gate)
    gate_a.name = "secrets"
    gate_a.check.side_effect = [False, False]
    gate_b = Mock(spec=Gate)
    gate_b.name = "network"
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[], gates=[gate_a, gate_b]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.GATE_APPLICATION_FAILURE
    assert gate_a.mock_calls == expected_calls(
        ("check", "enforce", "check", "release"), microjail
    )
    assert gate_b.mock_calls == []


def test_default_lockdown_application_enforces_network_drop(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    net = Mock(spec=Gate)
    net.name = "network-egress"
    net.check.side_effect = [False, True]
    ro = Mock(spec=Gate)
    ro.name = "readonly-config"
    ro.check.return_value = True
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[], gates=[net, ro]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.SUCCESS
    assert net.mock_calls == expected_calls(("check", "enforce", "check"), microjail)
    assert_calls([ro], ("check",), microjail)
