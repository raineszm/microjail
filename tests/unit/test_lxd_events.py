"""Tests for ``LxdEventWatcher``."""

import threading
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
    mock_connect.assert_called_once()
    mock_socket.close.assert_called()


def test_watcher_reconnects_after_disconnect_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On disconnect, the watcher waits 0.3s and reconnects, pushing a new sentinel."""
    # Arrange
    stop_iteration = threading.Event()

    socket_1 = Mock()
    socket_1.__iter__ = Mock(side_effect=ConnectionClosed(None, None))

    def block_iter() -> object:
        stop_iteration.wait()
        return iter([])

    socket_2 = Mock()
    socket_2.__iter__ = Mock(side_effect=block_iter)

    mock_connect = Mock(side_effect=[socket_1, socket_2])

    sleep_calls: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    # Act
    try:
        watcher.start()
        first = watcher.events.get(timeout=1.0)
        second = watcher.events.get(timeout=1.0)
    finally:
        stop_iteration.set()
        watcher.stop()

    # Assert
    assert first == "reconnect"
    assert second == "reconnect"
    assert sleep_calls == [0.3]


def test_watcher_raises_enforcement_lost_after_three_failed_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three consecutive failed connect attempts set LxdEnforcementLost as last_exception."""
    mock_connect = Mock(side_effect=Exception("connect failed"))
    sleep_calls: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleep_calls.append(s))

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    watcher.start()
    watcher.stop()

    assert isinstance(watcher.last_exception, LxdEnforcementLost)
    assert mock_connect.call_count == 3
    assert sleep_calls == [0.3, 0.5]


def test_watcher_passes_event_url_to_connect() -> None:
    """The watcher opens a WebSocket to the lifecycle event URL with the project query."""
    mock_socket = Mock()
    mock_connect = Mock(return_value=mock_socket)

    watcher = LxdEventWatcher(
        container_name="test-container",
        lxd_project="test-project",
        connect=mock_connect,
    )

    try:
        watcher.start()
        watcher.events.get(timeout=1.0)  # drain "reconnect"
    finally:
        watcher.stop()

    mock_connect.assert_called_once()
    (called_args, _called_kwargs) = mock_connect.call_args
    called_url = called_args[0]
    assert called_url.startswith("wss://127.0.0.1:8443/1.0/events?type=lifecycle")
    assert "project=test-project" in called_url


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
