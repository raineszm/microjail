"""Tests for ``MicroJail.pre_launch_verify()``."""

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from microjail.caps.endpoint import WorkshopEndpointCapability
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.lockdown import CapabilityError, GateError, Lockdown
from microjail.microjail import MicroJail, PreLaunchVerifyResult

if TYPE_CHECKING:
    from microjail.caps.base import Capability
    from microjail.gates.base import Gate


def make_microjail(gates: list[Gate], caps: list[Capability]) -> MicroJail:
    return MicroJail(
        workshop=Mock(name="Workshop"),
        lockdown=Lockdown(caps=caps, gates=gates),
    )


def test_returns_empty_result_on_empty_lockdown() -> None:
    mj = make_microjail(gates=[], caps=[])
    result = mj.pre_launch_verify()
    assert result == PreLaunchVerifyResult(non_fatal_capability_failures=())


def test_returns_empty_result_when_all_gates_and_caps_pass() -> None:
    gate = Mock(spec=NetworkDrop)
    gate.name = "g"
    gate.check.return_value = True
    gate.verify.return_value = True

    cap = Mock(spec=WorkshopEndpointCapability)
    cap.name = "c"
    cap.fatal = False
    cap.check.return_value = True
    cap.verify.return_value = True

    mj = make_microjail(gates=[gate], caps=[cap])
    result = mj.pre_launch_verify()
    assert result.non_fatal_capability_failures == ()


def test_raises_gate_error_on_first_failing_gate() -> None:
    g1 = Mock(spec=NetworkDrop)
    g1.name = "g1"
    g1.verify.return_value = True

    g2 = Mock(spec=ReadonlyConfig)
    g2.name = "g2"
    g2.verify.return_value = False

    g3 = Mock(spec=NetworkDrop)
    g3.name = "g3"
    g3.verify.return_value = True

    mj = make_microjail(gates=[g1, g2, g3], caps=[])

    with pytest.raises(GateError) as exc_info:
        mj.pre_launch_verify()
    assert exc_info.value.name == "g2"
    g3.verify.assert_not_called()


def test_raises_capability_error_on_failing_fatal_capability() -> None:
    cap = Mock(spec=WorkshopEndpointCapability)
    cap.name = "inference"
    cap.fatal = True
    cap.verify.return_value = False

    mj = make_microjail(gates=[], caps=[cap])

    with pytest.raises(CapabilityError) as exc_info:
        mj.pre_launch_verify()
    assert exc_info.value.name == "inference"


def test_collects_non_fatal_capability_failure_in_result() -> None:
    cap = Mock(spec=WorkshopEndpointCapability)
    cap.name = "optional-telemetry"
    cap.fatal = False
    cap.verify.return_value = False

    mj = make_microjail(gates=[], caps=[cap])

    result = mj.pre_launch_verify()
    assert result.non_fatal_capability_failures == ("optional-telemetry",)


def test_collects_multiple_non_fatal_capability_failures() -> None:
    cap_a = Mock(spec=WorkshopEndpointCapability)
    cap_a.name = "a"
    cap_a.fatal = False
    cap_a.verify.return_value = False

    cap_b = Mock(spec=WorkshopEndpointCapability)
    cap_b.name = "b"
    cap_b.fatal = False
    cap_b.verify.return_value = False

    cap_pass = Mock(spec=WorkshopEndpointCapability)
    cap_pass.name = "passing"
    cap_pass.fatal = False
    cap_pass.verify.return_value = True

    mj = make_microjail(gates=[], caps=[cap_a, cap_b, cap_pass])

    result = mj.pre_launch_verify()
    assert set(result.non_fatal_capability_failures) == {"a", "b"}


def test_fatal_capability_raises_before_non_fatal_is_collected() -> None:
    non_fatal = Mock(spec=WorkshopEndpointCapability)
    non_fatal.name = "optional"
    non_fatal.fatal = False
    non_fatal.verify.return_value = False

    fatal = Mock(spec=WorkshopEndpointCapability)
    fatal.name = "inference"
    fatal.fatal = True
    fatal.verify.return_value = False

    mj = make_microjail(gates=[], caps=[non_fatal, fatal])

    with pytest.raises(CapabilityError) as exc_info:
        mj.pre_launch_verify()
    assert exc_info.value.name == "inference"
