from unittest.mock import Mock, call

import pytest

from microjail.lockdown import GateError, Lockdown


def test_ensure_releases_applied_state_if_gate_verification_fails() -> None:
    cap = Mock()
    cap.name = "proxy"
    cap.check.side_effect = [False, True]

    good_gate = Mock()
    good_gate.name = "network"
    good_gate.check.side_effect = [False, True]

    bad_gate = Mock()
    bad_gate.name = "secrets"
    bad_gate.check.side_effect = [False, False]

    lockdown = Lockdown(caps=[cap], gates=[good_gate, bad_gate])

    with pytest.raises(GateError):
        lockdown.ensure()

    assert cap.mock_calls == [call.check(), call.provide(), call.check(), call.revoke()]
    assert good_gate.mock_calls == [
        call.check(),
        call.enforce(),
        call.check(),
        call.release(),
    ]
    assert bad_gate.mock_calls == [
        call.check(),
        call.enforce(),
        call.check(),
        call.release(),
    ]


def test_ensure_preserves_preexisting_state_if_later_gate_fails() -> None:
    cap = Mock()
    cap.name = "proxy"
    cap.check.side_effect = [True]

    existing_gate = Mock()
    existing_gate.name = "network"
    existing_gate.check.side_effect = [True]

    bad_gate = Mock()
    bad_gate.name = "secrets"
    bad_gate.check.side_effect = [False, False]

    lockdown = Lockdown(caps=[cap], gates=[existing_gate, bad_gate])

    with pytest.raises(GateError):
        lockdown.ensure()

    assert cap.mock_calls == [call.check()]
    assert existing_gate.mock_calls == [call.check()]
    assert bad_gate.mock_calls == [
        call.check(),
        call.enforce(),
        call.check(),
        call.release(),
    ]


def test_ensure_aborts_remaining_gates_after_first_failure() -> None:
    bad_gate = Mock()
    bad_gate.name = "secrets"
    bad_gate.check.side_effect = [False, False]

    skipped_gate = Mock()
    skipped_gate.name = "network"

    lockdown = Lockdown(caps=[], gates=[bad_gate, skipped_gate])

    with pytest.raises(GateError):
        lockdown.ensure()

    assert bad_gate.mock_calls == [
        call.check(),
        call.enforce(),
        call.check(),
        call.release(),
    ]
    assert skipped_gate.mock_calls == []
