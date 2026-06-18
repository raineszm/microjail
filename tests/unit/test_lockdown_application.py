from typing import TYPE_CHECKING, Literal
from unittest.mock import ANY, Mock

import pytest

from microjail.adapters import workshop
from microjail.adapters.workshop import Workshop
from microjail.caps.base import Capability
from microjail.gates.base import Gate
from microjail.lockdown import (
    CapabilityReleaseError,
    GateReleaseError,
    Lockdown,
)
from microjail.microjail import (
    ApplicationIntent,
    ApplicationStatus,
    MicroJail,
    WorkshopNotReadyError,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_microjail(tmp_path: Path, project_name: str) -> MicroJail:
    return MicroJail(
        workshop=Workshop(name=project_name, project=tmp_path),
        lockdown=Lockdown(caps=[], gates=[]),
    )


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

    capability.check.assert_not_called()
    gate.check.assert_not_called()


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

    capability.check.assert_not_called()
    gate.check.assert_not_called()


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
    capability.provide.assert_called_once_with(microjail, batch=ANY)
    gate.enforce.assert_called_once_with(microjail)


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
    cap.provide.assert_not_called()
    gate.enforce.assert_not_called()


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
    cap.check.side_effect = [False]
    cap.provide.side_effect = RuntimeError("provision failed")
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
    cap.provide.assert_called_once_with(microjail, batch=ANY)
    cap.revoke.assert_not_called()
    gate.enforce.assert_called_once_with(microjail)
    gate.release.assert_not_called()


def test_lock_application_gate_failure_keeps_capability_failures_as_context(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.side_effect = [False]
    cap.provide.side_effect = RuntimeError("provision failed")
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
    cap.provide.assert_called_once_with(microjail, batch=ANY)
    cap.revoke.assert_not_called()
    gate.enforce.assert_called_once_with(microjail)
    gate.release.assert_not_called()


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
    cap.provide.assert_not_called()
    gate_a.enforce.assert_not_called()
    gate_b.enforce.assert_called_once_with(microjail)
    gate_b.release.assert_called_once_with(microjail)


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
    gate_a.enforce.assert_called_once_with(microjail)
    gate_a.release.assert_called_once_with(microjail)
    gate_b.check.assert_not_called()


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
    net.enforce.assert_called_once_with(microjail)
    ro.enforce.assert_not_called()


def test_ensure_with_two_endpoint_caps_triggers_one_refresh(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    """Two real WorkshopEndpointCapability instances in ensure() produce one refresh."""
    from unittest.mock import PropertyMock

    from microjail.adapters.workshop import Workshop
    from microjail.caps.endpoint import WorkshopEndpointCapability
    from microjail.microjail import MicroJail

    cap_a = WorkshopEndpointCapability(name="inference", host_endpoint="127.0.0.1:8080")
    cap_b = WorkshopEndpointCapability(name="storage", host_endpoint="127.0.0.1:9090")
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap_a, cap_b], gates=[]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    mock_refresh = Mock()
    monkeypatch.setattr(microjail.workshop, "refresh", mock_refresh)
    mock_tunnel = Mock()
    mock_tunnel.connections.return_value = []
    mock_tunnel.endpoint_reachable.return_value = False
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    result = microjail.ensure(ApplicationIntent.LOCK)

    assert result.status is ApplicationStatus.SUCCESS
    assert mock_refresh.call_count == 1, (
        f"expected 1 refresh, got {mock_refresh.call_count}"
    )
    assert mock_tunnel.connect.call_count == 2
    assert mock_tunnel.add_plug.call_count == 2
    assert mock_tunnel.add_slot.call_count == 2


def test_ensure_zero_caps_triggers_no_refresh(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    """Ensure() with zero endpoint capabilities skips refresh entirely."""
    from unittest.mock import PropertyMock

    from microjail.adapters.workshop import Workshop
    from microjail.microjail import MicroJail

    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[], gates=[]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    mock_refresh = Mock()
    monkeypatch.setattr(microjail.workshop, "refresh", mock_refresh)
    mock_tunnel = Mock()
    monkeypatch.setattr(Workshop, "tunnel", PropertyMock(return_value=mock_tunnel))

    result = microjail.ensure(ApplicationIntent.LOCK)

    assert result.status is ApplicationStatus.SUCCESS
    mock_refresh.assert_not_called()
    mock_tunnel.connect.assert_not_called()


def test_run_application_rolls_back_if_capability_provision_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_microjail: MicroJail
) -> None:
    """Ensure(RUN) with a failing capability still rolls back."""
    from microjail.microjail import MicroJail

    cap = Mock(spec=Capability)
    cap.name = "proxy"
    cap.check.side_effect = [False]
    cap.provide.side_effect = RuntimeError("provision failed")
    microjail = MicroJail(
        workshop=Workshop(name=tmp_microjail.name, project=tmp_microjail.project_path),
        lockdown=Lockdown(caps=[cap], gates=[]),
    )
    mark_workshop_ready(monkeypatch, microjail)

    result = microjail.ensure(ApplicationIntent.RUN)

    assert result.status is ApplicationStatus.CAPABILITY_APPLICATION_FAILURE
    assert [error.name for error in result.capability_failures] == ["proxy"]
    assert result.rollback_failures == ()
    cap.provide.assert_called_once_with(microjail, batch=ANY)
    cap.revoke.assert_called_once_with(microjail)
