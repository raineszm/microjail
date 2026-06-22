"""Tests for the event-driven ``Warden``."""

import queue
import subprocess
from unittest.mock import Mock

import pytest

from microjail.adapters.lxd_events import LxdEnforcementLost
from microjail.microjail import MicroJail
from microjail.warden import GatePolicyViolation, Warden


def make_warden(
    *,
    events: queue.Queue[str] | None = None,
    watcher: Mock | None = None,
    process: Mock | None = None,
    gates: list[Mock] | None = None,
    caps: list[Mock] | None = None,
) -> Warden:
    microjail = Mock(spec=MicroJail)
    microjail.lockdown = Mock()
    microjail.lockdown.gates = gates if gates is not None else []
    microjail.lockdown.caps = caps if caps is not None else []
    return Warden(
        microjail=microjail,
        process=process or Mock(spec=subprocess.Popen),
        events=events if events is not None else queue.Queue(),
        watcher=watcher,
    )


def make_gate(name: str, check_result: bool) -> Mock:
    gate = Mock()
    gate.name = name
    gate.check.return_value = check_result
    return gate


def test_warden_returns_exit_code_when_process_terminates() -> None:
    process = Mock(spec=subprocess.Popen)
    process.wait.return_value = 0
    warden = make_warden(process=process)

    assert warden.supervise() == 0
    process.wait.assert_called_once_with(timeout=0.1)


def test_warden_returns_non_zero_exit_code() -> None:
    process = Mock(spec=subprocess.Popen)
    process.wait.return_value = 7
    warden = make_warden(process=process)

    assert warden.supervise() == 7


def test_warden_drains_event_and_rechecks_gates() -> None:
    events: queue.Queue[str] = queue.Queue()
    events.put("reconnect")

    process = Mock(spec=subprocess.Popen)
    process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.1),
        0,
    ]

    gate = make_gate("network-egress", check_result=True)
    microjail = Mock(spec=MicroJail)
    microjail.lockdown = Mock()
    microjail.lockdown.gates = [gate]
    microjail.lockdown.caps = []

    warden = Warden(
        microjail=microjail,
        process=process,
        events=events,
    )

    assert warden.supervise() == 0
    gate.check.assert_called_once_with(microjail)


def test_warden_terminates_on_gate_violation_in_drain() -> None:
    events: queue.Queue[str] = queue.Queue()
    events.put("reconnect")

    process = Mock(spec=subprocess.Popen)
    process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.1),
        None,
    ]
    process.poll.return_value = None

    gate = make_gate("network-egress", check_result=False)
    microjail = Mock(spec=MicroJail)
    microjail.lockdown = Mock()
    microjail.lockdown.gates = [gate]
    microjail.lockdown.caps = []

    warden = Warden(
        microjail=microjail,
        process=process,
        events=events,
    )

    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    process.terminate.assert_called_once()


def test_warden_drains_multiple_events_in_a_row() -> None:
    events: queue.Queue[str] = queue.Queue()
    events.put("reconnect")
    events.put("instance-updated")

    process = Mock(spec=subprocess.Popen)
    process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.1),
        0,
    ]

    gate = make_gate("network-egress", check_result=True)
    microjail = Mock(spec=MicroJail)
    microjail.lockdown = Mock()
    microjail.lockdown.gates = [gate]
    microjail.lockdown.caps = []

    warden = Warden(
        microjail=microjail,
        process=process,
        events=events,
    )

    assert warden.supervise() == 0
    assert gate.check.call_count == 2


def test_warden_does_not_check_capabilities_at_runtime() -> None:
    """The capability loop is removed from the Warden entirely."""
    process = Mock(spec=subprocess.Popen)
    process.wait.return_value = 0

    cap = Mock()
    cap.name = "endpoint"

    warden = make_warden(process=process, caps=[cap])

    assert warden.supervise() == 0
    cap.check.assert_not_called()
    cap.verify.assert_not_called()


def test_warden_escalates_on_lxd_enforcement_lost() -> None:
    events: queue.Queue[str] = queue.Queue()

    process = Mock(spec=subprocess.Popen)
    process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.1),
        None,
    ]
    process.poll.return_value = None

    watcher = Mock()
    watcher.last_exception = LxdEnforcementLost("lost")
    watcher.is_alive.return_value = False

    warden = make_warden(process=process, events=events, watcher=watcher)

    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    process.terminate.assert_called_once()
