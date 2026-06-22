"""The Warden: event-driven runtime supervisor for a workload under Lockdown."""

import contextlib
import queue
import subprocess
from typing import TYPE_CHECKING

from microjail.adapters.lxd_events import LxdEnforcementLost

if TYPE_CHECKING:
    from microjail.microjail import MicroJail


SUPERVISE_POLL_INTERVAL = 0.1


class GatePolicyViolation(Exception):
    """Raised when a gate policy violation is detected at runtime."""


class Warden:
    """Runtime supervisor for executing workloads under an applied Lockdown.

    The Warden multiplexes between the workload's :class:`subprocess.Popen`
    handle and the :class:`LxdEventWatcher` event queue. On every LXD
    lifecycle event (and on every ``"reconnect"`` sentinel from the watcher),
    every gate's :meth:`check` is re-run. The first failing gate terminates
    the workload and escalates as a :class:`GatePolicyViolation`.

    Capabilities are launch-time only and are *not* monitored at runtime.
    Loss of the LXD event subscription escalates as a
    :class:`GatePolicyViolation` (RUNTIME_GATE_POLICY_VIOLATION, 84) —
    under the threat model "LXD is the only thing that can enforce," a
    workload we cannot supervise is a security regression.
    """

    def __init__(
        self,
        microjail: MicroJail,
        process: subprocess.Popen,
        events: queue.Queue[str],
        watcher: object | None = None,
    ) -> None:
        self.microjail = microjail
        self.process = process
        self.events = events
        self.watcher = watcher

    def supervise(self) -> int:
        """Supervise the workload process and block until it terminates."""
        while True:
            try:
                return self.process.wait(timeout=SUPERVISE_POLL_INTERVAL)
            except subprocess.TimeoutExpired:
                self._poll()

    def _poll(self) -> None:
        """Drain pending events and validate every gate."""
        self._raise_if_enforcement_lost()
        for _ in self._drain_events():
            for gate in self.microjail.lockdown.gates:
                try:
                    gate_passed = gate.check(self.microjail)
                except Exception as exc:
                    self._terminate_safely()
                    raise GatePolicyViolation(
                        f"Gate policy violation: unable to verify {gate.name}"
                    ) from exc
                if not gate_passed:
                    self._terminate_safely()
                    raise GatePolicyViolation(f"Gate policy violation: {gate.name}")

    def _drain_events(self) -> list[str]:
        """Pop every pending event from the queue, non-blocking."""
        drained: list[str] = []
        while True:
            try:
                drained.append(self.events.get_nowait())
            except queue.Empty:
                return drained

    def _raise_if_enforcement_lost(self) -> None:
        """Re-raise :class:`LxdEnforcementLost` if the watcher died with one."""
        exc = getattr(self.watcher, "last_exception", None)
        if isinstance(exc, LxdEnforcementLost):
            self._terminate_safely()
            raise GatePolicyViolation(
                f"Gate policy violation: lost LXD event subscription "
                f"for {self.microjail.name}"
            ) from exc

    def _terminate_safely(self) -> None:
        """Terminate the workload, swallowing any error from the terminate path.

        The Warden has already decided to escalate (gate violation or
        enforcement lost). A failure inside :meth:`terminate_workload`
        — for instance ``lxc stop --force`` failing because LXD is
        unreachable, which is the same condition that triggered the
        escalation — cannot change that decision and must not mask the
        security-relevant exception. The supervisor's caller will
        translate the :class:`GatePolicyViolation` to exit code 84.
        """
        with contextlib.suppress(Exception):
            self.terminate_workload()

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
