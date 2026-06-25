import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from microjail.adapters.lxd_monitor import LifecycleEvent, LxdMonitor

if TYPE_CHECKING:
    from collections.abc import Callable

    from microjail.microjail import MicroJail


class _LxdMonitorLike(Protocol):
    """Structural type for any object usable as an ``LxdMonitor`` by the Warden.

    Both the real :class:`LxdMonitor` and test doubles (e.g.
    ``FakeLxdMonitor``) satisfy this protocol structurally, so test factories
    can return a duck-typed stand-in without inheriting from ``LxdMonitor``.
    """

    def __iter__(self) -> _LxdMonitorLike: ...
    def __next__(self) -> LifecycleEvent: ...
    def close(self) -> None: ...


class GatePolicyViolation(Exception):
    """Raised when a gate policy violation is detected at runtime."""


class CapabilityPolicyViolation(Exception):
    """Raised when a fatal capability policy violation is detected at runtime."""


@dataclass(frozen=True)
class MonitorError:
    """Wrapper pushed by pump_events when it captures an unexpected exception."""

    exception: BaseException


def pump_events(mon, event_queue, stop) -> None:
    """Iterate `mon`, push events to the queue. Push None on EOF.

    Unexpected exceptions are captured and pushed as MonitorError so the
    supervision thread can re-raise them on the main thread.
    """
    try:
        for event in mon:
            if stop.is_set():
                return
            event_queue.put(event)
    except StopIteration:
        pass
    except BaseException as exc:
        event_queue.put(MonitorError(exception=exc))
        return
    event_queue.put(None)


class Warden:
    """Runtime supervisor for executing workloads under an applied Lockdown.

    The `monitor_factory` kwarg is the test injection point: tests pass a fake
    factory that returns a real blocking iterator (not a Mock) so the supervision
    loop can be exercised without spawning a real `lxc monitor` subprocess.
    """

    def __init__(
        self,
        microjail: MicroJail,
        process: subprocess.Popen,
        interval: float = 1.0,
        monitor_factory: Callable[[str, str], _LxdMonitorLike] | None = None,
    ) -> None:
        self.microjail = microjail
        self.process = process
        self.interval = interval
        self.monitor_factory: Callable[[str, str], _LxdMonitorLike] = (
            monitor_factory if monitor_factory is not None else LxdMonitor
        )

    def supervise(self) -> int:
        """Supervise the workload process and block until it terminates."""
        self.check_policies()

        mon = self.monitor_factory(
            self.microjail.container_name(), self.microjail.lxd_project()
        )
        event_queue: queue.Queue[object] = queue.Queue()
        stop = threading.Event()
        try:
            pump = threading.Thread(
                target=pump_events,
                args=(mon, event_queue, stop),
                daemon=True,
                name="warden-lxd-monitor-pump",
            )
            pump.start()
            while True:
                try:
                    return self.process.wait(timeout=self.interval)
                except subprocess.TimeoutExpired:
                    pass
                while True:
                    try:
                        item = event_queue.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        self.terminate_workload()
                        raise GatePolicyViolation("LXD event monitor stream closed")
                    if isinstance(item, MonitorError):
                        raise item.exception from item.exception
                self.check_policies()
        finally:
            stop.set()
            mon.close()

    def check_policies(self) -> None:
        """Inspect all active gates and capabilities."""
        for gate in self.microjail.lockdown.gates:
            try:
                ok = gate.check(self.microjail)
            except BaseException:
                self.terminate_workload()
                raise GatePolicyViolation(
                    f"Gate policy violation: {gate.name}"
                ) from None
            if not ok:
                self.terminate_workload()
                raise GatePolicyViolation(f"Gate policy violation: {gate.name}")

        for cap in self.microjail.lockdown.caps:
            try:
                ok = cap.check(self.microjail)
            except BaseException:
                ok = False
            if not ok:
                if getattr(cap, "fatal", False):
                    self.terminate_workload()
                    raise CapabilityPolicyViolation(
                        f"Capability policy violation: {cap.name}"
                    )
                else:
                    import sys

                    print(
                        f"Warning: Capability policy violation: {cap.name}",
                        file=sys.stderr,
                    )

    def terminate_workload(self) -> None:
        """Terminate the workload process and escalate to container force stop if needed."""
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            from microjail.adapters import lxc

            container = self.microjail.container_name()
            project = self.microjail.lxd_project()
            lxc.stop_instance(container, project, force=True)
