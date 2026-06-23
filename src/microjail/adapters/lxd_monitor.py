"""LXD lifecycle event subscription for the Warden.

The :class:`LxdMonitor` exposes LXD lifecycle events for a single container and
LXD project as a blocking iterator over an ``lxc monitor`` subprocess. The
caller iterates with a ``for`` loop and gets one :class:`LifecycleEvent` per
iteration. Threading and queueing are out of scope; the caller can wrap the
iterator in a thread + queue if parallel consumption is needed.
"""

import subprocess

import msgspec

from microjail.adapters.executor import CommandExecutor, LocalExecutor


class LifecycleMetadata(msgspec.Struct, frozen=True):
    """Action and resource identification for one LXD lifecycle event."""

    action: str
    source: str
    name: str | None = None
    project: str | None = None
    context: dict | None = None
    requestor: dict | None = None


class LifecycleEvent(msgspec.Struct, frozen=True):
    """One LXD lifecycle event, parsed from one line of ``lxc monitor --format=json``."""

    type: str
    timestamp: str
    location: str
    project: str
    metadata: LifecycleMetadata


def parse_event(line: str) -> LifecycleEvent:
    """Parse one ``lxc monitor --format=json`` line into a :class:`LifecycleEvent`."""
    return msgspec.json.decode(line, type=LifecycleEvent)


_INSTANCE_PREFIX = "/1.0/instances/"


def matches(event: LifecycleEvent, container_name: str, lxd_project: str) -> bool:
    """Return True if *event* is a lifecycle event for this monitor's container and project."""
    if event.type != "lifecycle":
        return False
    if event.project != lxd_project:
        return False
    if not event.metadata.source.startswith(_INSTANCE_PREFIX):
        return False
    return event.metadata.source.split("/")[3] == container_name


class LxdMonitor:
    """Watch LXD lifecycle events for a single container via ``lxc monitor``.

    The monitor owns a subprocess running
    ``lxc monitor --project=<project> --type=lifecycle --format=json`` and
    exposes matching events as a blocking iterator. Iterate with a ``for`` loop
    and call :meth:`close` (or use as a context manager) to terminate the
    subprocess.
    """

    def __init__(
        self,
        container_name: str,
        lxd_project: str,
        executor: CommandExecutor | None = None,
    ) -> None:
        self.container_name = container_name
        self.lxd_project = lxd_project
        self._executor: CommandExecutor = executor or LocalExecutor()
        self._process: subprocess.Popen | None = None

    def __iter__(self) -> LxdMonitor:
        """Start the ``lxc monitor`` subprocess and return self for iteration."""
        cmd = [
            "lxc",
            "monitor",
            f"--project={self.lxd_project}",
            "--type=lifecycle",
            "--format=json",
        ]
        self._process = self._executor.popen(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return self

    def __next__(self) -> LifecycleEvent:
        """Block for the next matching event, or raise ``StopIteration`` on EOF."""
        process = self._process
        if process is None or process.stdout is None:
            raise StopIteration
        while True:
            line = process.stdout.readline()
            if not line:
                raise StopIteration
            if not line.strip():
                continue
            event = parse_event(line)
            if matches(event, self.container_name, self.lxd_project):
                return event

    def __enter__(self) -> LxdMonitor:
        """Return self; iteration is what spawns the subprocess."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Terminate the subprocess when the ``with`` block exits."""
        self.close()

    def close(self) -> None:
        """Terminate the subprocess. Idempotent."""
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._process = None
