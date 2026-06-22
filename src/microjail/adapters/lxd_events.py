"""LXD lifecycle event subscription for the Warden."""

import contextlib
import json
import queue
import threading
import time
from typing import TYPE_CHECKING, Any

import websockets.sync.client

if TYPE_CHECKING:
    from collections.abc import Callable


class LxdEnforcementLost(Exception):
    """Raised when the watcher can no longer subscribe to LXD lifecycle events."""


RECONNECT_BACKOFFS: tuple[float, ...] = (0.3, 0.5)

# Default LXD event WebSocket path on a local daemon. The watcher uses
# this with ``lxd_local_connect`` (which loads the ``lxc`` CLI's client
# cert) for production; tests inject a ``connect`` mock instead.
DEFAULT_EVENT_URL = "wss://127.0.0.1:8443/1.0/events?type=lifecycle"


class LxdEventWatcher:
    """Watch LXD lifecycle events for a single container.

    The watcher owns a WebSocket subscription to ``GET /1.0/events?type=lifecycle``
    and pushes matching events onto a thread-safe queue. The Warden drains the
    queue on its supervision loop.

    Client-side filtering drops events whose ``metadata.name`` is not this
    watcher's container or whose ``metadata.project`` is not this watcher's
    LXD project, so the Warden only reacts to events for the workload it
    supervises.

    On unrecoverable loss of the subscription the watcher's reader thread
    captures the :class:`LxdEnforcementLost` in :attr:`last_exception` and
    exits; the Warden reads this attribute on its next poll and escalates.
    """

    def __init__(
        self,
        container_name: str,
        lxd_project: str,
        connect: Callable[..., Any] | None = None,
        event_url: str = DEFAULT_EVENT_URL,
    ) -> None:
        self.container_name = container_name
        self.lxd_project = lxd_project
        self.event_url = event_url
        self._connect: Callable[..., Any] = (
            connect if connect is not None else websockets.sync.client.connect
        )
        self.events: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_exception: BaseException | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        try:
            self._run_loop()
        except LxdEnforcementLost as exc:
            self.last_exception = exc

    def _run_loop(self) -> None:
        attempt = 0
        url = self._event_url()
        while not self._stop_event.is_set():
            try:
                ws = self._connect(url)
            except Exception:
                if attempt >= len(RECONNECT_BACKOFFS):
                    self._raise_enforcement_lost()
                time.sleep(RECONNECT_BACKOFFS[attempt])
                attempt += 1
                continue
            self.events.put("reconnect")
            attempt = 0
            try:
                for event in ws:
                    if self._stop_event.is_set():
                        break
                    if self._matches(event):
                        self.events.put(event)
            except Exception:
                pass
            with contextlib.suppress(Exception):
                ws.close()
            if self._stop_event.is_set():
                return
            if attempt >= len(RECONNECT_BACKOFFS):
                self._raise_enforcement_lost()
            time.sleep(RECONNECT_BACKOFFS[attempt])
            attempt += 1

    def _event_url(self) -> str:
        """Return the WebSocket URL to connect to.

        The project is appended as a query parameter so the watcher's
        subscription is scoped to its LXD project, in addition to the
        client-side ``metadata.project`` filter.
        """
        separator = "&" if "?" in self.event_url else "?"
        return f"{self.event_url}{separator}project={self.lxd_project}"

    def _matches(self, event: object) -> bool:
        """Return True if *event* is a lifecycle event for this watcher's container."""
        if not isinstance(event, str):
            return False
        try:
            data = json.loads(event)
        except TypeError, ValueError:
            return False
        if not isinstance(data, dict):
            return False
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            return False
        return (
            metadata.get("name") == self.container_name
            and metadata.get("project") == self.lxd_project
        )

    def _raise_enforcement_lost(self) -> None:
        raise LxdEnforcementLost(
            f"Lost LXD event subscription for {self.container_name}"
        )
