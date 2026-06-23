from unittest.mock import Mock

import pytest

from microjail.caps.base import Capability
from microjail.gates.base import Gate
from microjail.lockdown import CapabilityError, GateError, Lockdown
from microjail.microjail import MicroJail, PreLaunchVerifyResult


def test_pre_launch_verify_success() -> None:
    # GIVEN a lockdown where everything succeeds
    gate1 = Mock(spec=Gate)
    gate1.verify.return_value = True
    cap1 = Mock(spec=Capability)
    cap1.verify.return_value = True
    cap1.fatal = False

    mj = Mock(spec=MicroJail)
    mj.lockdown = Lockdown(caps=[cap1], gates=[gate1])

    # WHEN pre_launch_verify is called
    # THEN it returns successfully with no warnings
    result = MicroJail.pre_launch_verify(mj)
    assert isinstance(result, PreLaunchVerifyResult)
    assert result.non_fatal_capability_failures == ()


def test_pre_launch_verify_gate_failure() -> None:
    # GIVEN a lockdown with a failing gate
    gate1 = Mock(spec=Gate)
    gate1.name = "gate-one"
    gate1.verify.return_value = False
    gate2 = Mock(spec=Gate)  # Should not be verified

    mj = Mock(spec=MicroJail)
    mj.lockdown = Lockdown(caps=[], gates=[gate1, gate2])

    # WHEN pre_launch_verify is called
    # THEN it raises GateError for the first failing gate
    with pytest.raises(GateError) as exc_info:
        MicroJail.pre_launch_verify(mj)
    assert exc_info.value.name == "gate-one"
    gate2.verify.assert_not_called()


def test_pre_launch_verify_fatal_capability_failure() -> None:
    # GIVEN a lockdown with a fatal capability failure
    cap1 = Mock(spec=Capability)
    cap1.name = "cap-fatal"
    cap1.verify.return_value = False
    cap1.fatal = True
    cap2 = Mock(spec=Capability)  # Should not be verified

    mj = Mock(spec=MicroJail)
    mj.lockdown = Lockdown(caps=[cap1, cap2], gates=[])

    # WHEN pre_launch_verify is called
    # THEN it raises CapabilityError
    with pytest.raises(CapabilityError) as exc_info:
        MicroJail.pre_launch_verify(mj)
    assert exc_info.value.name == "cap-fatal"
    assert exc_info.value.non_fatal_failures == ()
    cap2.verify.assert_not_called()


def test_pre_launch_verify_non_fatal_capability_failures() -> None:
    # GIVEN a lockdown with non-fatal capability failures
    cap1 = Mock(spec=Capability)
    cap1.name = "cap-warn1"
    cap1.verify.return_value = False
    cap1.fatal = False
    cap2 = Mock(spec=Capability)
    cap2.name = "cap-warn2"
    cap2.verify.return_value = False
    cap2.fatal = False

    mj = Mock(spec=MicroJail)
    mj.lockdown = Lockdown(caps=[cap1, cap2], gates=[])

    # WHEN pre_launch_verify is called
    # THEN it returns warnings and doesn't raise
    result = MicroJail.pre_launch_verify(mj)
    assert result.non_fatal_capability_failures == ("cap-warn1", "cap-warn2")


def test_pre_launch_verify_fatal_retains_preceding_non_fatal_failures() -> None:
    # GIVEN non-fatal failures preceding a fatal failure
    cap1 = Mock(spec=Capability)
    cap1.name = "cap-warn"
    cap1.verify.return_value = False
    cap1.fatal = False
    cap2 = Mock(spec=Capability)
    cap2.name = "cap-fatal"
    cap2.verify.return_value = False
    cap2.fatal = True

    mj = Mock(spec=MicroJail)
    mj.lockdown = Lockdown(caps=[cap1, cap2], gates=[])

    # WHEN pre_launch_verify is called
    # THEN the raised CapabilityError carries the preceding failures
    with pytest.raises(CapabilityError) as exc_info:
        MicroJail.pre_launch_verify(mj)
    assert exc_info.value.name == "cap-fatal"
    assert exc_info.value.non_fatal_failures == ("cap-warn",)
