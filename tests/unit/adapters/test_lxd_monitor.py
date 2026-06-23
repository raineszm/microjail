"""Tests for the LXD event monitor adapter.

Layout:
- Component tests: ``test_matches_*`` cover the small, pure building blocks.
- Slice tests: ``test_lxd_monitor_*`` cover end-to-end behaviors of the
  :class:`LxdMonitor` iterator.

These tests use fake subprocesses (not mocks) injected through the public
``CommandExecutor`` injection point. The fakes implement the same protocol as
the real :class:`microjail.adapters.executor.CommandExecutor` enough for the
monitor to read lines, terminate, and end the iterator cleanly.
"""

import json
import subprocess
from typing import Any, cast

import pytest

from microjail.adapters.lxd_monitor import (
    LifecycleEvent,
    LifecycleMetadata,
    LxdMonitor,
    matches,
)

# --- Test fakes ------------------------------------------------------------


class _LineStream:
    """A file-like object that yields preset lines and then returns EOF."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self.closed = False

    def readline(self) -> str:
        if self.closed or not self._lines:
            return ""
        return self._lines.pop(0)

    def close(self) -> None:
        self.closed = True


class _FakePopen:
    """A stand-in for ``subprocess.Popen`` with a controllable stdout stream."""

    def __init__(
        self,
        cmd: list[str],
        stdout: _LineStream | None = None,
        *,
        wait_raises_timeout: bool = False,
        **_: Any,
    ) -> None:
        self.cmd = cmd
        self.stdout = stdout
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self.waited: list[float | None] = []
        self.wait_raises_timeout = wait_raises_timeout
        self.wait_calls = 0

    def terminate(self) -> None:
        self.terminated = True
        if self.stdout is not None:
            self.stdout.close()

    def kill(self) -> None:
        self.killed = True
        if self.stdout is not None:
            self.stdout.close()

    def wait(self, timeout: float | None = None) -> int:
        self.waited.append(timeout)
        self.wait_calls += 1
        if self.wait_raises_timeout and self.wait_calls == 1:
            raise subprocess.TimeoutExpired(cmd=self.cmd, timeout=timeout or 0.0)
        return self.returncode if self.returncode is not None else 0


class _FakeExecutor:
    """A ``CommandExecutor`` that records the command and returns a preset Popen."""

    def __init__(self, popen: _FakePopen) -> None:
        self.popen_instance = popen
        self.popen_calls: list[tuple[list[str], dict[str, Any]]] = []

    def popen(self, command: list[str], **kwargs: Any) -> Any:
        self.popen_calls.append((command, kwargs))
        return cast("Any", self.popen_instance)

    def run(self, command: list[str], **kwargs: Any) -> Any:
        raise NotImplementedError


def _lifecycle_line(
    *,
    action: str = "instance-started",
    container: str = "agent",
    project: str = "workshop",
    event_type: str = "lifecycle",
) -> str:
    return json.dumps(
        {
            "location": "none",
            "metadata": {
                "action": action,
                "name": container,
                "project": project,
                "requestor": {
                    "address": "@",
                    "protocol": "unix",
                    "username": "workshop",
                },
                "source": f"/1.0/instances/{container}",
            },
            "project": project,
            "timestamp": "2026-06-23T12:48:52.066853564-05:00",
            "type": event_type,
        }
    )


# --- Component: matches -----------------------------------------------------


def _event(
    *,
    type: str = "lifecycle",
    project: str = "workshop",
    source: str = "/1.0/instances/agent",
    action: str = "instance-started",
) -> LifecycleEvent:
    return LifecycleEvent(
        type=type,
        timestamp="2026-06-23T12:48:52.066853564-05:00",
        location="none",
        project=project,
        metadata=LifecycleMetadata(action=action, source=source),
    )


def test_matches_returns_true_for_matching_container_and_project() -> None:
    # Arrange
    event = _event(project="workshop", source="/1.0/instances/agent")

    # Act / Assert
    assert matches(event, container_name="agent", lxd_project="workshop") is True


def test_matches_returns_false_for_non_lifecycle_type() -> None:
    # Arrange
    event = _event(type="logging", source="/1.0/instances/agent")

    # Act / Assert
    assert matches(event, container_name="agent", lxd_project="workshop") is False


def test_matches_returns_false_for_different_container() -> None:
    # Arrange
    event = _event(source="/1.0/instances/other")

    # Act / Assert
    assert matches(event, container_name="agent", lxd_project="workshop") is False


def test_matches_returns_false_for_different_project() -> None:
    # Arrange
    event = _event(project="other-project")

    # Act / Assert
    assert matches(event, container_name="agent", lxd_project="workshop") is False


def test_matches_returns_false_for_non_instance_source() -> None:
    # Arrange — e.g. a network lifecycle event, not an instance
    event = _event(source="/1.0/networks/my-net")

    # Act / Assert
    assert matches(event, container_name="agent", lxd_project="workshop") is False


# --- Slice 1 (Tracer Bullet): end-to-end iteration --------------------------


def test_lxd_monitor_iteration_yields_matching_lifecycle_event() -> None:
    # Arrange
    line = _lifecycle_line()
    stream = _LineStream([line])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )

    # Act
    iter(monitor)
    try:
        event = next(monitor)
    finally:
        monitor.close()

    # Assert
    assert isinstance(event, LifecycleEvent)
    assert event.metadata.action == "instance-started"
    assert event.metadata.source == "/1.0/instances/agent"


# --- Slice 2: Iterator skips non-matching events ---------------------------


def test_lxd_monitor_skips_non_matching_events() -> None:
    # Arrange — one matching event among several non-matching ones
    lines = [
        _lifecycle_line(action="instance-started", container="other"),
        _lifecycle_line(action="instance-started", project="other-project"),
        _lifecycle_line(action="instance-started", event_type="logging"),
        _lifecycle_line(action="instance-started", container="agent"),
    ]
    stream = _LineStream(lines)
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )
    # Act — iterate until StopIteration
    try:
        events = list(monitor)
    finally:
        monitor.close()

    # Assert — only the one matching event was delivered
    assert len(events) == 1
    assert events[0].metadata.source == "/1.0/instances/agent"
    assert events[0].metadata.action == "instance-started"


# --- Slice 3: StopIteration on EOF -----------------------------------------


def test_lxd_monitor_raises_stop_iteration_on_subprocess_eof() -> None:
    # Arrange — empty stdout: EOF on first readline
    stream = _LineStream([])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )

    # Act
    iter(monitor)
    try:
        with pytest.raises(StopIteration):
            next(monitor)
    finally:
        monitor.close()


# --- Slice 4: close() terminates the subprocess and is idempotent ------------


def test_lxd_monitor_close_terminates_subprocess() -> None:
    # Arrange
    stream = _LineStream([])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )
    iter(monitor)

    # Act
    monitor.close()

    # Assert
    assert popen.terminated is True


def test_lxd_monitor_close_is_idempotent() -> None:
    # Arrange
    stream = _LineStream([])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )
    iter(monitor)

    # Act — close twice
    monitor.close()
    monitor.close()

    # Assert — no exception
    assert popen.terminated is True


# --- Slice 5: CommandExecutor injection shape ------------------------------


def test_lxd_monitor_uses_injected_command_executor_with_expected_command() -> None:
    # Arrange
    stream = _LineStream([])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )

    # Act
    iter(monitor)
    try:
        # Assert
        assert len(executor.popen_calls) == 1
        cmd, kwargs = executor.popen_calls[0]
        assert cmd == [
            "lxc",
            "monitor",
            "--project=workshop",
            "--type=lifecycle",
            "--format=json",
        ]
        assert kwargs["stdout"] is not None
        assert kwargs["text"] is True
        assert kwargs["bufsize"] == 1
    finally:
        monitor.close()


# --- Slice 6: Context manager -----------------------------------------------


def test_lxd_monitor_context_manager_terminates_subprocess_on_block_exit() -> None:
    # Arrange
    stream = _LineStream([])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)

    # Act
    with LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    ) as monitor:
        iter(monitor)

    # Assert
    assert popen.terminated is True


def test_lxd_monitor_context_manager_terminates_subprocess_on_exception() -> None:
    # Arrange
    stream = _LineStream([])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    with (
        pytest.raises(RuntimeError, match="boom"),
        LxdMonitor(
            container_name="agent", lxd_project="workshop", executor=executor
        ) as monitor,
    ):
        iter(monitor)
        raise RuntimeError("boom")
    assert popen.terminated is True


# --- Slice 1 addition: single-use guard ------------------------------------


def test_lxd_monitor_raises_runtime_error_on_double_iter() -> None:
    # Arrange
    stream = _LineStream([])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )
    iter(monitor)

    # Act / Assert — second call to iter() while the subprocess is running
    # must raise RuntimeError, not spawn a second subprocess.
    with pytest.raises(RuntimeError, match="single-use"):
        iter(monitor)
    assert len(executor.popen_calls) == 1
    monitor.close()


# --- Slice 1 addition: blank lines are silently skipped --------------------


def test_lxd_monitor_skips_blank_lines_in_stdout() -> None:
    # Arrange — blank lines (single newline / whitespace) interleaved with a
    # matching event. The fake returns these as the lines themselves, and
    # readline() returns "" only on EOF, not for blank lines.
    lines = [
        "\n",
        "   \n",
        _lifecycle_line(),
    ]
    stream = _LineStream(lines)
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )

    # Act
    iter(monitor)
    try:
        event = next(monitor)
    finally:
        monitor.close()

    # Assert — the matching event was delivered; the blank lines were
    # silently consumed without affecting event delivery.
    assert event.metadata.action == "instance-started"


# --- Slice 4 addition: kill() fallback when wait() times out ---------------


def test_lxd_monitor_close_kills_subprocess_when_terminate_times_out() -> None:
    # Arrange — wait() raises TimeoutExpired on the first call (terminate
    # path), forcing close() to escalate to kill().
    stream = _LineStream([])
    popen = _FakePopen(cmd=[], stdout=stream, wait_raises_timeout=True)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )
    iter(monitor)

    # Act
    monitor.close()

    # Assert
    assert popen.terminated is True
    assert popen.killed is True
    assert popen.wait_calls == 2


# --- Slice 3 addition: StopIteration after close() -------------------------


def test_lxd_monitor_raises_stop_iteration_after_close() -> None:
    # Arrange
    stream = _LineStream([_lifecycle_line()])
    popen = _FakePopen(cmd=[], stdout=stream)
    executor = _FakeExecutor(popen)
    monitor = LxdMonitor(
        container_name="agent", lxd_project="workshop", executor=executor
    )
    iter(monitor)

    # Act — close, then call next() again
    monitor.close()
    with pytest.raises(StopIteration):
        next(monitor)
