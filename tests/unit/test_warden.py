import os
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, call

import pytest

from microjail import policy
from microjail.adapters.lxd_monitor import LifecycleEvent, LifecycleMetadata
from microjail.adapters.workshop import Workshop
from microjail.microjail import MicroJail
from microjail.warden import CapabilityPolicyViolation, GatePolicyViolation, Warden

if TYPE_CHECKING:
    from collections.abc import Generator


def fake_factory(_container_name: str, _lxd_project: str) -> FakeLxdMonitor:
    return FakeLxdMonitor()


def test_warden_supervises_successful_exit() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.return_value = 0

    warden = Warden(mock_mj, mock_process, interval=0.01, monitor_factory=fake_factory)

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    mock_process.wait.assert_called_once_with(timeout=0.01)


def test_warden_supervises_non_zero_exit() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.return_value = 42

    warden = Warden(mock_mj, mock_process, interval=0.01, monitor_factory=fake_factory)

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 42
    mock_process.wait.assert_called_once_with(timeout=0.01)


def test_warden_polls_on_interval() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    mock_gate.check.return_value = True

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = True

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = [mock_cap]

    mock_process = Mock(spec=subprocess.Popen)
    # We raise TimeoutExpired twice, then exit with 0
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    warden = Warden(mock_mj, mock_process, interval=0.01, monitor_factory=fake_factory)

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    assert mock_gate.check.call_count == 3
    assert mock_cap.check.call_count == 3
    mock_gate.check.assert_has_calls([call(mock_mj), call(mock_mj)])
    mock_cap.check.assert_has_calls([call(mock_mj), call(mock_mj)])


def test_warden_terminates_on_gate_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    # Returns True on first check, False on second
    mock_gate.check.side_effect = [True, False]

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = True

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = [mock_cap]
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = Mock(spec=subprocess.Popen)
    # Baseline check passes (gate True), then first event-check fails (gate False).
    # First wait times out (triggers event-check), second wait is the terminate's
    # wait(timeout=2) which also times out -> escalation -> lxc.stop_instance.
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        subprocess.TimeoutExpired(cmd="terminate", timeout=2),
    ]

    mock_stop_instance = Mock()
    monkeypatch.setattr(
        "microjail.adapters.lxc.stop_instance", mock_stop_instance, raising=False
    )

    warden = Warden(mock_mj, mock_process, interval=0.01, monitor_factory=fake_factory)

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    # Check that process termination was called
    mock_process.terminate.assert_called_once()
    # Wait should be called to wait for process termination with timeout of 2 seconds
    mock_process.wait.assert_any_call(timeout=2)


def test_warden_terminates_on_gate_violation_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    mock_gate.check.return_value = False

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = []
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = Mock(spec=subprocess.Popen)
    # First wait times out (initiates policy check)
    # During terminate, we wait again, which also times out (escalation)
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        subprocess.TimeoutExpired(cmd="terminate", timeout=2),
    ]

    mock_stop_instance = Mock()
    monkeypatch.setattr(
        "microjail.adapters.lxc.stop_instance", mock_stop_instance, raising=False
    )

    warden = Warden(mock_mj, mock_process, interval=0.01, monitor_factory=fake_factory)

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    # Check process termination and container stop
    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)
    mock_stop_instance.assert_called_once_with(
        "test-container", "test-project", force=True
    )


def test_warden_warns_on_non_fatal_capability_violation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    mock_cap.check.return_value = False
    mock_cap.fatal = False

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = [mock_cap]

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    warden = Warden(mock_mj, mock_process, interval=0.01, monitor_factory=fake_factory)

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    mock_process.terminate.assert_not_called()

    captured = capsys.readouterr()
    assert "Warning: Capability policy violation" in captured.err
    assert "mock-cap" in captured.err


def test_warden_terminates_on_fatal_capability_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.lockdown = Mock()

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    # Baseline check passes (True), then first event-check fails (False) -> fatal violation
    mock_cap.check.side_effect = [True, False]
    mock_cap.fatal = True

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = [mock_cap]
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    mock_stop_instance = Mock()
    monkeypatch.setattr(
        "microjail.adapters.lxc.stop_instance", mock_stop_instance, raising=False
    )

    warden = Warden(mock_mj, mock_process, interval=0.01, monitor_factory=fake_factory)

    # Act & Assert
    with pytest.raises(CapabilityPolicyViolation):
        warden.supervise()

    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)


class FakeLxdMonitor:
    """Test double for LxdMonitor: real blocking iterator (not a Mock).

    Mirrors the real LxdMonitor's single-use contract: ``__iter__`` may only
    be called once per instance. Re-iterating after the monitor has been
    opened raises RuntimeError, matching ``LxdMonitor.__iter__`` in
    ``src/microjail/adapters/lxd_monitor.py``. This is a regression guard
    for the event-driven Warden: the supervision thread must never call
    ``iter(mon)`` itself — only the pump thread iterates the monitor via
    its ``for event in mon:`` loop.

    ``__next__`` blocks on a threading.Event until deliver() is called or
    close() is called (in which case it raises StopIteration).
    """

    def __init__(self) -> None:
        self._events: deque[LifecycleEvent] = deque()
        self._wake = threading.Event()
        self._closed = False
        self.close_calls = 0
        self._iterated = False

    def __iter__(self) -> FakeLxdMonitor:
        if self._iterated:
            raise RuntimeError(
                "FakeLxdMonitor is single-use: __iter__ cannot be called while "
                "a subprocess is already running"
            )
        self._iterated = True
        return self

    def __next__(self) -> LifecycleEvent:
        while not self._events:
            if self._closed:
                raise StopIteration
            self._wake.clear()
            self._wake.wait()
        return self._events.popleft()

    def deliver(self, event: LifecycleEvent) -> None:
        self._events.append(event)
        self._wake.set()

    def close(self) -> None:
        self._closed = True
        self.close_calls += 1
        self._wake.set()

    @property
    def closed(self) -> bool:
        return self._closed


def test_warden_event_driven_passes_through_successful_exit() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    mock_process.wait.return_value = 0

    fake_monitor = FakeLxdMonitor()
    monitor_factory = Mock(return_value=fake_monitor)

    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    mock_process.wait.assert_called_once_with(timeout=0.01)
    assert fake_monitor.closed is True
    monitor_factory.assert_called_once_with("test-container", "test-project")


def test_warden_rechecks_policies_on_lxd_event() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    # Baseline check passes (True); the event-triggered check fails (False).
    mock_gate.check.side_effect = [True, False]

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    # First wait times out -> queue drained, event-triggered check raises.
    # Second wait is the terminate's wait(timeout=2) -> workload exited cleanly.
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    fake_monitor = FakeLxdMonitor()
    event = LifecycleEvent(
        type="lifecycle",
        timestamp="2026-01-01T00:00:00Z",
        location="test-location",
        project="test-project",
        metadata=LifecycleMetadata(
            action="test", source="/1.0/instances/test-container"
        ),
    )
    fake_monitor.deliver(event)
    monitor_factory = Mock(return_value=fake_monitor)
    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    # The gate was checked twice: once at baseline, once after the event was drained.
    assert mock_gate.check.call_count == 2
    mock_process.terminate.assert_called_once()
    assert fake_monitor.closed is True


def test_warden_rechecks_policies_on_fallback_interval_when_monitor_quiet() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    mock_gate.check.return_value = True

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    # Two timeouts trigger two check_policies calls; then workload exits cleanly.
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    fake_monitor = FakeLxdMonitor()  # quiet: no events delivered
    monitor_factory = Mock(return_value=fake_monitor)
    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    # Baseline (1) + two fallback polls (2) = 3 checks
    assert mock_gate.check.call_count == 3
    assert fake_monitor.closed is True


def test_warden_baseline_catches_pre_existing_gate_violation() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    mock_gate.check.return_value = False  # baseline fails immediately

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    # No wait() calls expected: baseline raises before the loop starts.
    mock_process.wait.return_value = 0

    monitor_factory = Mock(side_effect=AssertionError("factory must not be called"))
    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    # The monitor must never have been opened: the factory was not called.
    monitor_factory.assert_not_called()
    # The baseline check must have terminated the workload.
    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)


def test_warden_terminates_on_gate_violation_in_event_path() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    # Baseline passes; event-triggered check fails.
    mock_gate.check.side_effect = [True, False]

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    # First wait times out -> queue drained, event-triggered check raises.
    # Second wait is the terminate's wait(timeout=2) -> workload exited cleanly.
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    fake_monitor = FakeLxdMonitor()
    event = LifecycleEvent(
        type="lifecycle",
        timestamp="2026-01-01T00:00:00Z",
        location="test-location",
        project="test-project",
        metadata=LifecycleMetadata(
            action="test", source="/1.0/instances/test-container"
        ),
    )
    fake_monitor.deliver(event)
    monitor_factory = Mock(return_value=fake_monitor)
    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)


def test_warden_escalates_gate_violation_in_event_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()

    mock_gate = Mock()
    mock_gate.name = "mock-gate"
    mock_gate.check.side_effect = [True, False]

    mock_mj.lockdown.gates = [mock_gate]
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    # First wait times out -> event-triggered check raises.
    # Second wait is the terminate's wait(timeout=2) which also times out -> escalation.
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        subprocess.TimeoutExpired(cmd="terminate", timeout=2),
    ]

    mock_stop_instance = Mock()
    monkeypatch.setattr(
        "microjail.adapters.lxc.stop_instance", mock_stop_instance, raising=False
    )

    fake_monitor = FakeLxdMonitor()
    event = LifecycleEvent(
        type="lifecycle",
        timestamp="2026-01-01T00:00:00Z",
        location="test-location",
        project="test-project",
        metadata=LifecycleMetadata(
            action="test", source="/1.0/instances/test-container"
        ),
    )
    fake_monitor.deliver(event)
    monitor_factory = Mock(return_value=fake_monitor)
    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act & Assert
    with pytest.raises(GatePolicyViolation):
        warden.supervise()

    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)
    mock_stop_instance.assert_called_once_with(
        "test-container", "test-project", force=True
    )
    assert fake_monitor.closed is True


def test_warden_warns_on_non_fatal_capability_violation_in_event_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    # Baseline passes; event-triggered check fails (non-fatal).
    mock_cap.check.side_effect = [True, False]
    mock_cap.fatal = False

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = [mock_cap]

    mock_process = Mock(spec=subprocess.Popen)
    # First wait times out -> queue drained, event-triggered check warns.
    # Second wait returns the workload's exit code.
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    fake_monitor = FakeLxdMonitor()
    event = LifecycleEvent(
        type="lifecycle",
        timestamp="2026-01-01T00:00:00Z",
        location="test-location",
        project="test-project",
        metadata=LifecycleMetadata(
            action="test", source="/1.0/instances/test-container"
        ),
    )
    fake_monitor.deliver(event)
    monitor_factory = Mock(return_value=fake_monitor)
    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act
    exit_code = warden.supervise()

    # Assert
    assert exit_code == 0
    mock_process.terminate.assert_not_called()

    captured = capsys.readouterr()
    assert "Warning: Capability policy violation" in captured.err
    assert "mock-cap" in captured.err
    assert fake_monitor.closed is True


def test_warden_terminates_on_fatal_capability_violation_in_event_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()

    mock_cap = Mock()
    mock_cap.name = "mock-cap"
    # Baseline passes; event-triggered check fails (fatal).
    mock_cap.check.side_effect = [True, False]
    mock_cap.fatal = True

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = [mock_cap]

    mock_process = Mock(spec=subprocess.Popen)
    # First wait times out -> event-triggered check raises fatal violation.
    # Second wait is the terminate's wait(timeout=2) -> workload exited cleanly.
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    mock_stop_instance = Mock()
    monkeypatch.setattr(
        "microjail.adapters.lxc.stop_instance", mock_stop_instance, raising=False
    )

    fake_monitor = FakeLxdMonitor()
    event = LifecycleEvent(
        type="lifecycle",
        timestamp="2026-01-01T00:00:00Z",
        location="test-location",
        project="test-project",
        metadata=LifecycleMetadata(
            action="test", source="/1.0/instances/test-container"
        ),
    )
    fake_monitor.deliver(event)
    monitor_factory = Mock(return_value=fake_monitor)
    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act & Assert
    with pytest.raises(CapabilityPolicyViolation):
        warden.supervise()

    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)
    assert fake_monitor.closed is True


def test_warden_treats_monitor_stream_loss_as_gate_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = "test-container"
    mock_mj.lxd_project.return_value = "test-project"
    mock_mj.lockdown = Mock()

    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    mock_process = Mock(spec=subprocess.Popen)
    # First wait times out -> drain queue, find None sentinel -> raise.
    # Second wait is the terminate's wait(timeout=2) -> workload exited cleanly.
    mock_process.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=0.01),
        0,
    ]

    mock_stop_instance = Mock()
    monkeypatch.setattr(
        "microjail.adapters.lxc.stop_instance", mock_stop_instance, raising=False
    )

    fake_monitor = FakeLxdMonitor()
    # Signal EOF BEFORE supervise() runs so the pump thread sees it immediately.
    fake_monitor.close()
    monitor_factory = Mock(return_value=fake_monitor)
    warden = Warden(
        mock_mj, mock_process, interval=0.01, monitor_factory=monitor_factory
    )

    # Act & Assert
    with pytest.raises(GatePolicyViolation, match="LXD event monitor stream closed"):
        warden.supervise()

    mock_process.terminate.assert_called_once()
    mock_process.wait.assert_any_call(timeout=2)
    # The Warden's finally called close() on the monitor.
    assert fake_monitor.close_calls >= 1


def test_warden_default_monitor_factory_is_lxd_monitor_class() -> None:
    # Arrange
    mock_mj = Mock(spec=MicroJail)
    mock_process = Mock(spec=subprocess.Popen)

    warden = Warden(mock_mj, mock_process, interval=0.01)

    # Assert: the default factory is the LxdMonitor class itself.
    from microjail.adapters.lxd_monitor import LxdMonitor

    assert warden.monitor_factory is LxdMonitor


# -- end-to-end tests against real Workshop --
#
# The unit tests above exercise the supervision loop with a fake monitor.
# These tests prove the wiring against real LXD: a real ``lxc monitor``
# subprocess delivers a lifecycle event, the Warden's pump thread enqueues
# it, the supervision thread drains the queue and re-runs
# ``check_policies()``, and a violation terminates the workload with the
# expected CLI exit code. They are marked slow + lxd + workshop; the root
# conftest skips them when ``--slow`` is not passed or LXD / Workshop are
# unavailable.

VIOLATION_TIMEOUT = 30.0
# Time for the Warden to start ``lxc monitor`` and apply lockdown after
# the workload has spawned. The window between workload start and monitor
# ready is short; 2s is more than enough on a normal system.
MONITOR_WARMUP = 2.0


@pytest.fixture
def e2e_warden_workshop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Workshop]:
    """A launched Workshop with a microjail config; auto-cleans after the test."""
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-warden-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()
    MicroJail.init(name, project_path=project)
    ws = Workshop(name=name, project=project)
    ws.launch()
    monkeypatch.chdir(project)
    try:
        yield ws
    finally:
        os.chdir(cwd)
        mj = MicroJail.load(project)
        mj.destroy()


def add_nic_via_lxd(container: str, project: str, device: str = "eth0") -> None:
    """Attach a NIC device to the container from the host.

    LXD broadcasts a ``lifecycle`` event for ``instance-updated`` on this
    container; the Warden's LxdMonitor should match the event, the pump
    thread should enqueue it, and the next ``check_policies()`` should
    notice the NIC is back and raise ``GatePolicyViolation``.

    Uses ``nictype=p2p`` so the test does not depend on a real bridge
    being available; any NIC type triggers the same LXD event.
    """
    subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "config",
            "device",
            "add",
            container,
            device,
            "nic",
            "nictype=p2p",
        ],
        check=True,
        capture_output=True,
    )


def remove_nic_via_lxd(container: str, project: str, device: str = "eth0") -> None:
    """Best-effort detach of the test NIC for cleanup."""
    subprocess.run(
        [
            "lxc",
            "--project",
            project,
            "config",
            "device",
            "remove",
            container,
            device,
        ],
        check=False,
        capture_output=True,
    )


@pytest.mark.slow
@pytest.mark.lxd
@pytest.mark.workshop
def test_warden_event_driven_terminates_on_runtime_nic_attach(
    e2e_warden_workshop: Workshop,
) -> None:
    """Warden must terminate the workload when a NIC is attached mid-run.

    This is the bug class the change exists to fix: polling could miss a
    device that is added and removed inside a single interval. An e2e
    test that demonstrates the event-driven path catching a real LXD
    event against a real container is the strongest evidence the wiring
    is correct end-to-end.
    """
    container = e2e_warden_workshop.container_name()
    assert container is not None
    project = e2e_warden_workshop.lxd_project

    proc = subprocess.Popen(
        ["microjail", "exec", "--", "sleep", "30"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Give the Warden time to start the lxc monitor and apply lockdown.
        time.sleep(MONITOR_WARMUP)
        # The workload must still be running before the violation trigger.
        assert proc.poll() is None, "workload exited before NIC attach"

        # Attach a NIC mid-run; this is the trigger the Warden must catch.
        add_nic_via_lxd(container, project)

        try:
            _stdout, stderr = proc.communicate(timeout=VIOLATION_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            _stdout, stderr = proc.communicate()
            pytest.fail(
                f"workload did not exit within {VIOLATION_TIMEOUT}s after NIC attach; "
                f"event-driven path did not fire; stderr={stderr!r}"
            )
    finally:
        remove_nic_via_lxd(container, project)

    assert proc.returncode == policy.RUNTIME_GATE_POLICY_VIOLATION, (
        f"expected RUNTIME_GATE_POLICY_VIOLATION "
        f"({policy.RUNTIME_GATE_POLICY_VIOLATION}), "
        f"got {proc.returncode}; stderr={stderr!r}"
    )


@pytest.mark.slow
@pytest.mark.lxd
@pytest.mark.workshop
def test_warden_event_driven_clean_exit_no_hang(
    e2e_warden_workshop: Workshop,
) -> None:
    """A workload that exits before any LXD events must still complete cleanly.

    Exercises the pump-thread shutdown path with a real ``lxc monitor``
    subprocess: the workload exits, the supervision loop returns the
    exit code, the ``finally`` block closes the monitor, and the pump
    thread winds down. A hang here would indicate the pump thread or
    monitor close path is broken under real subprocess semantics.
    """
    result = subprocess.run(
        ["microjail", "exec", "--", "true"],
        capture_output=True,
        text=True,
        timeout=30.0,
    )

    assert result.returncode == 0, (
        f"clean workload exited {result.returncode}: {result.stderr}"
    )


@pytest.mark.slow
@pytest.mark.lxd
@pytest.mark.workshop
def test_warden_event_driven_long_running_workload_does_not_reiterate_monitor(
    e2e_warden_workshop: Workshop,
) -> None:
    """A workload that outlives the monitor warmup must not crash the Warden.

    Regression test: the supervision thread must iterate the LxdMonitor
    *exactly once*. The real LxdMonitor's ``__iter__`` raises
    ``RuntimeError("LxdMonitor is single-use")`` if called while a
    subprocess is already running. Earlier the supervision thread called
    ``iter(mon)`` explicitly and the pump thread also iterated the same
    monitor via its ``for event in mon:`` loop, causing a crash roughly
    one second into any workload that lived past the first interval.

    ``sleep 2`` is long enough for the pump thread to have started, called
    ``iter(mon)``, and been blocked in ``readline()`` for a full interval
    tick. Under the bug the Warden would crash with exit code 1 (the
    RuntimeError propagating out of supervise_workload). With the fix
    the workload completes cleanly with exit code 0.
    """
    result = subprocess.run(
        ["microjail", "exec", "--", "sleep", "2"],
        capture_output=True,
        text=True,
        timeout=30.0,
    )

    assert result.returncode == 0, (
        f"long-running workload exited {result.returncode}; "
        f"this often indicates the Warden double-iterated the LxdMonitor. "
        f"stderr={result.stderr!r}"
    )
