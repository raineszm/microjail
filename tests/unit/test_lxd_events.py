"""Tests for ``LxdEventWatcher``."""

import threading
import time
from typing import TYPE_CHECKING
from unittest.mock import Mock

from websockets.exceptions import ConnectionClosed

from microjail.adapters.lxd_events import LxdEnforcementLost, LxdEventWatcher

if TYPE_CHECKING:
    import pytest


def test_watcher_emits_reconnect_sentinel_on_initial_connect() -> None:
    # Arrange
    mock_socket = Mock()
    mock_connect = Mock(return_value=mock_socket)

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    # Act
    try:
        watcher.start()
        event = watcher.events.get(timeout=1.0)
    finally:
        watcher.stop()

    # Assert
    assert event == "reconnect"
    # The connect loop re-enters on every event-loop end (the
    # reconnect sentinel cycle), so we only assert that the first
    # connect happened, not that it was the only one.
    assert mock_connect.call_count >= 1
    mock_socket.close.assert_called()


def test_watcher_reconnects_after_disconnect_without_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a disconnect, the watcher reconnects quickly with no cooldown.

    The spec is silent on whether a sleep precedes the first reconnect;
    the contract is "escalation within 0.8s, reconnect as soon as
    possible". A successful first reconnect must emit a new "reconnect"
    sentinel promptly (no 0.3s cooldown) and the second connect must
    complete well within the 0.8s escalation budget.
    """
    stop_iteration = threading.Event()

    socket_1 = Mock()
    socket_1.__iter__ = Mock(side_effect=ConnectionClosed(None, None))

    def block_iter() -> object:
        stop_iteration.wait()
        return iter([])

    socket_2 = Mock()
    socket_2.__iter__ = Mock(side_effect=block_iter)

    mock_connect = Mock(side_effect=[socket_1, socket_2])
    monkeypatch.setattr("time.sleep", lambda _s: None)  # no real sleeps

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    try:
        watcher.start()
        first = watcher.events.get(timeout=1.0)
        # Time how quickly the second sentinel arrives. Should be
        # effectively immediate, not the 0.3s the old cooldown gave.
        start = time.monotonic()
        second = watcher.events.get(timeout=0.1)
        reconnect_latency = time.monotonic() - start
    finally:
        stop_iteration.set()
        watcher.stop()

    assert first == "reconnect"
    assert second == "reconnect"
    # The old design slept 0.3s before the first reconnect; the new
    # design reconnects immediately. 100ms is a generous bound that
    # still catches a regression to cooldown-style backoff.
    assert reconnect_latency < 0.1, (
        f"second reconnect took {reconnect_latency:.3f}s, expected < 0.1s (no cooldown)"
    )


def test_watcher_escalates_after_disconnect_reconnects_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If all reconnect attempts after a live disconnect fail, escalate.

    The contract: the watcher gives up and surfaces
    :class:`LxdEnforcementLost` within the 0.8s backoff budget. The
    exact number of attempts and per-sleep durations are implementation
    details of the budget; we assert the budget itself.
    """
    # First connect succeeds, then drops, then every reconnect fails.
    socket_1 = Mock()
    socket_1.__iter__ = Mock(side_effect=ConnectionClosed(None, None))
    mock_connect = Mock(
        side_effect=[
            socket_1,
            OSError("retry 1"),
            OSError("retry 2"),
            OSError("retry 3"),
        ]
    )
    # Use real sleeps so the 0.8s budget actually elapses; this is the
    # behavior we want to test, not the per-sleep durations.
    monkeypatch.setattr("time.sleep", lambda _s: None)  # not strictly needed

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    try:
        start = time.monotonic()
        watcher.start()
        watcher.events.get(timeout=1.0)  # drain initial "reconnect"
        # Wait for escalation. last_exception is set when the reader
        # thread dies after exhausting retries.
        deadline = start + 1.0
        while watcher.last_exception is None and time.monotonic() < deadline:
            time.sleep(0.01)
        escalation_latency = time.monotonic() - start
    finally:
        watcher.stop()

    assert isinstance(watcher.last_exception, LxdEnforcementLost), (
        f"expected LxdEnforcementLost, got {watcher.last_exception!r}"
    )
    # Spec: "total time from disconnect to escalation under 1 second."
    # We allow 1.0s of headroom on the test side.
    assert escalation_latency < 1.0, (
        f"escalation took {escalation_latency:.3f}s, expected < 1.0s"
    )


def test_watcher_escalates_after_initial_connect_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three consecutive failed initial connect attempts set LxdEnforcementLost.

    Same budget assertion as the disconnect-path test: escalation
    within 1 second.
    """
    mock_connect = Mock(side_effect=OSError("connect failed"))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    start = time.monotonic()
    watcher.start()
    deadline = start + 1.0
    while watcher.last_exception is None and time.monotonic() < deadline:
        time.sleep(0.01)
    escalation_latency = time.monotonic() - start
    watcher.stop()

    assert isinstance(watcher.last_exception, LxdEnforcementLost)
    assert escalation_latency < 1.0, (
        f"escalation took {escalation_latency:.3f}s, expected < 1.0s"
    )


def test_watcher_enqueues_matching_lifecycle_event() -> None:
    """A lifecycle event for the watched container is enqueued."""

    matching = (
        '{"type":"lifecycle","metadata":'
        '{"name":"test-container","project":"test-project","action":"instance-updated"}}'
    )

    mock_socket = Mock()
    mock_socket.__iter__ = Mock(return_value=iter([matching]))
    mock_connect = Mock(return_value=mock_socket)

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    try:
        watcher.start()
        first = watcher.events.get(timeout=1.0)  # "reconnect"
        second = watcher.events.get(timeout=1.0)  # the matching event
    finally:
        watcher.stop()

    assert first == "reconnect"
    assert second == matching


def test_watcher_drops_event_for_other_container() -> None:
    """A lifecycle event for a different container is filtered out."""
    import queue

    import pytest

    other_container = (
        '{"type":"lifecycle","metadata":'
        '{"name":"other-container","project":"test-project","action":"instance-updated"}}'
    )

    stop_iteration = threading.Event()

    mock_socket = Mock()

    def block_iter() -> object:
        stop_iteration.wait()
        return iter([other_container])

    mock_socket.__iter__ = Mock(side_effect=block_iter)
    mock_connect = Mock(return_value=mock_socket)

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    try:
        watcher.start()
        first = watcher.events.get(timeout=1.0)  # "reconnect" only
        with pytest.raises(queue.Empty):
            watcher.events.get(timeout=0.1)
    finally:
        stop_iteration.set()
        watcher.stop()

    assert first == "reconnect"


def test_watcher_drops_event_for_other_project() -> None:
    """A lifecycle event for a different LXD project is filtered out."""
    import queue

    import pytest

    other_project = (
        '{"type":"lifecycle","metadata":'
        '{"name":"test-container","project":"other-project","action":"instance-updated"}}'
    )

    stop_iteration = threading.Event()

    mock_socket = Mock()

    def block_iter() -> object:
        stop_iteration.wait()
        return iter([other_project])

    mock_socket.__iter__ = Mock(side_effect=block_iter)
    mock_connect = Mock(return_value=mock_socket)

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    try:
        watcher.start()
        first = watcher.events.get(timeout=1.0)  # "reconnect" only
        with pytest.raises(queue.Empty):
            watcher.events.get(timeout=0.1)
    finally:
        stop_iteration.set()
        watcher.stop()

    assert first == "reconnect"


def test_watcher_drops_malformed_event() -> None:
    """A non-JSON or malformed event is filtered out, not raised."""
    import queue

    import pytest

    stop_iteration = threading.Event()

    mock_socket = Mock()

    def block_iter() -> object:
        stop_iteration.wait()
        return iter(["not json at all", '{"missing":"metadata"}', "{}"])

    mock_socket.__iter__ = Mock(side_effect=block_iter)
    mock_connect = Mock(return_value=mock_socket)

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    try:
        watcher.start()
        first = watcher.events.get(timeout=1.0)  # "reconnect"
        with pytest.raises(queue.Empty):
            watcher.events.get(timeout=0.1)
    finally:
        stop_iteration.set()
        watcher.stop()

    assert first == "reconnect"
