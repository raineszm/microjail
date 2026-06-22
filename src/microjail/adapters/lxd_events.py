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

    Client-side filtering drops events whose instance source is not this
    watcher's container or whose top-level project is not this watcher's LXD
    project, so the Warden only reacts to events for the workload it supervises.

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
        # The currently-open WebSocket, if any. The reader writes it
        # on connect and clears it on stream end. :meth:`stop` closes
        # it from the caller's thread to unblock the read so the join
        self._ws: Any | None = None
        # ``last_exception`` is written by the reader thread and read
        # by the Warden on its own thread. The GIL makes single
        # attribute writes/reads atomic in CPython, so no extra
        # lock is needed today. If we ever target free-threaded
        # Python, this needs a ``threading.Lock``.
        self.last_exception: BaseException | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                ws.close()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        try:
            self._run_loop()
        except LxdEnforcementLost as exc:
            self.last_exception = exc

    def _run_loop(self) -> None:
        url = self._event_url()
        while not self._stop_event.is_set():
            self._ws = self._connect_with_retries(url)
            self.events.put("reconnect")
            self._drain_until_stopped(self._ws)
            with contextlib.suppress(Exception):
                self._ws.close()
            self._ws = None

    def _drain_until_stopped(self, ws: Any) -> None:
        """Iterate *ws* events until :attr:`_stop_event` is set or the stream ends.

        Uses an explicit ``next()`` loop (not ``for event in ws``) so the
        stop check runs even when the iterator is empty or yields nothing.
        Without this, a mock socket with an empty ``__iter__`` would let
        the connect loop re-enter forever even after :meth:`stop` is
        called. A non-iterable *ws* is treated as an immediately-ended
        stream; any exception from ``next()`` (closed socket, protocol
        error) is also treated as a stream end so the connect loop can
        re-enter or stop.
        """
        try:
            iterator = iter(ws)
        except Exception:
            return
        while not self._stop_event.is_set():
            try:
                event = next(iterator)
            except Exception:
                return
            if self._matches(event):
                self.events.put(event)

    def _connect_with_retries(self, url: str) -> Any:
        """Open a WebSocket, retrying with bounded backoff.

        Makes up to ``len(RECONNECT_BACKOFFS) + 1`` connect attempts
        (three total) with a sleep between each failed attempt taken
        from :data:`RECONNECT_BACKOFFS` (0.3s, 0.5s). The total time
        from first failure to escalation is bounded to 0.8s. If all
        three attempts fail, raises :class:`LxdEnforcementLost`.
        """
        last_exc: BaseException | None = None
        for attempt in range(len(RECONNECT_BACKOFFS) + 1):
            try:
                return self._connect(url)
            except Exception as exc:
                last_exc = exc
                if attempt < len(RECONNECT_BACKOFFS):
                    time.sleep(RECONNECT_BACKOFFS[attempt])
        raise LxdEnforcementLost(
            f"Lost LXD event subscription for {self.container_name}"
        ) from last_exc

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
        event_project = data.get("project", metadata.get("project"))
        event_container = metadata.get("name")
        source = metadata.get("source")
        if event_container is None and isinstance(source, str):
            event_container = self._container_name_from_source(source)
        return (
            event_container == self.container_name and event_project == self.lxd_project
        )

    def _container_name_from_source(self, source: str) -> str | None:
        """Return an instance name from an LXD lifecycle ``metadata.source`` path."""
        prefix = "/1.0/instances/"
        if not source.startswith(prefix):
            return None
        return source.removeprefix(prefix).split("/", maxsplit=1)[0].split("?", 1)[0]

    def _raise_enforcement_lost(self) -> None:
        raise LxdEnforcementLost(
            f"Lost LXD event subscription for {self.container_name}"
        )
