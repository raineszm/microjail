"""End-to-end tests for the LXD event watcher against a real LXD daemon.

These tests run ``microjail exec`` via :class:`typer.testing.CliRunner` in
a thread so a real LXD action can be interleaved with the workload while
the watcher's WebSocket is live. The ``CliRunner`` invokes the CLI in
process; nothing here shells out to a ``microjail`` binary.
"""

import json
import queue
import threading
import time
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from microjail import policy
from microjail.adapters.lxc import add_device, lxd_local_connect
from microjail.adapters.lxd_events import LxdEventWatcher
from microjail.cli import app

if TYPE_CHECKING:
    from microjail.adapters.workshop import Workshop


WORKLOAD_READY_TIMEOUT = 15.0
WORKLOAD_RUN_TIMEOUT = 20.0
WORKLOAD_POLL_INTERVAL = 0.1
LXD_EVENT_TIMEOUT = 10.0


def wait_for_workload_signal(ws: Workshop, signal_path: str) -> None:
    """Block until *signal_path* appears inside the workshop container."""
    deadline = time.monotonic() + WORKLOAD_READY_TIMEOUT
    while time.monotonic() < deadline:
        result = ws.exec_(["test", "-f", signal_path], check=False)
        if result.returncode == 0:
            return
        time.sleep(WORKLOAD_POLL_INTERVAL)
    msg = f"workload signal {signal_path} did not appear in workshop {ws.name}"
    raise TimeoutError(msg)


def wait_for_lxd_event(watcher: LxdEventWatcher) -> str:
    """Block until the watcher emits a real LXD event, ignoring reconnect sentinels."""
    deadline = time.monotonic() + LXD_EVENT_TIMEOUT
    while time.monotonic() < deadline:
        if watcher.last_exception is not None:
            raise watcher.last_exception
        try:
            event = watcher.events.get(timeout=WORKLOAD_POLL_INTERVAL)
        except queue.Empty:
            continue
        if event != "reconnect":
            return event
    msg = "LXD lifecycle event did not arrive before timeout"
    raise TimeoutError(msg)


def wait_for_lxd_subscription(watcher: LxdEventWatcher) -> None:
    """Block until the watcher reports a successful LXD event subscription."""
    deadline = time.monotonic() + LXD_EVENT_TIMEOUT
    while time.monotonic() < deadline:
        if watcher.last_exception is not None:
            raise watcher.last_exception
        try:
            event = watcher.events.get(timeout=WORKLOAD_POLL_INTERVAL)
        except queue.Empty:
            continue
        if event == "reconnect":
            return
    msg = "LXD lifecycle subscription did not connect before timeout"
    raise TimeoutError(msg)


def test_watcher_observes_real_lxd_device_event(e2e_workshop: Workshop) -> None:
    """The watcher receives real LXD lifecycle events for host-side config changes."""
    lock_result = CliRunner().invoke(app, ["lock"])
    assert lock_result.exit_code == 0, lock_result.stderr

    container = e2e_workshop.container_name()
    assert container is not None

    watcher = LxdEventWatcher(
        container_name=container,
        lxd_project=e2e_workshop.lxd_project,
        connect=lxd_local_connect,
    )

    try:
        watcher.start()
        wait_for_lxd_subscription(watcher)
        add_device(
            container=container,
            device="event-probe",
            config={"type": "nic", "nictype": "bridged", "parent": "workshopbr0"},
            project=e2e_workshop.lxd_project,
        )
        event = wait_for_lxd_event(watcher)
    finally:
        watcher.stop()

    data = json.loads(event)
    assert data["project"] == e2e_workshop.lxd_project
    assert data["metadata"]["source"].startswith(f"/1.0/instances/{container}")
    assert f"project={e2e_workshop.lxd_project}" in data["metadata"]["source"]
    assert data["metadata"]["action"] == "instance-updated"


def test_external_lxd_event_triggers_gate_escalation(
    e2e_workshop: Workshop,
) -> None:
    """Adding a NIC while a workload is running escalates as a gate violation.

    Lock the workshop (zero NICs after lockdown), run a long-lived workload
    under ``microjail exec`` so the watcher subscribes to LXD lifecycle
    events, then attach a NIC device from the host. The watcher must
    observe the lifecycle event, the Warden's gate re-check must see the
    NIC, and the workload must be terminated with exit code 84
    (``RUNTIME_GATE_POLICY_VIOLATION``).
    """
    # Lockdown first: NetworkDrop removes every NIC from the container.
    lock_result = CliRunner().invoke(app, ["lock"])
    assert lock_result.exit_code == 0, lock_result.stderr

    # Run ``microjail exec`` in a thread so we can fire an LXD action
    # while the workload is alive. CliRunner captures the exit code into
    # ``captured`` when the command returns.
    captured: dict[str, int] = {}

    def run_workload() -> None:
        result = CliRunner().invoke(
            app,
            [
                "exec",
                "--",
                "sh",
                "-c",
                "touch /tmp/watcher-ready; sleep 30",
            ],
        )
        captured["exit_code"] = result.exit_code

    supervisor = threading.Thread(target=run_workload, daemon=True)
    supervisor.start()

    # Wait for the workload process to actually be running inside
    # the container before we touch LXD. The ``touch`` lands before
    # ``microjail exec`` returns control past pre_launch_verify.
    wait_for_workload_signal(e2e_workshop, "/tmp/watcher-ready")

    # Attach a NIC from the host. This fires a lifecycle event that
    # the watcher must observe. The container's existing profile
    # uses ``workshopbr0`` so we re-use the same parent.
    container = e2e_workshop.container_name()
    assert container is not None  # workshop is launched
    add_device(
        container=container,
        device="evil-egress",
        config={"type": "nic", "nictype": "bridged", "parent": "workshopbr0"},
        project=e2e_workshop.lxd_project,
    )

    supervisor.join(timeout=WORKLOAD_RUN_TIMEOUT)
    # No cleanup needed: if the supervisor thread is still alive at this
    # point, the e2e_workshop fixture destroys the workshop on
    # teardown, which kills the workload and the watcher.

    assert not supervisor.is_alive(), (
        "workload supervisor did not terminate after LXD event"
    )
    assert captured["exit_code"] == policy.RUNTIME_GATE_POLICY_VIOLATION, (
        f"expected exit {policy.RUNTIME_GATE_POLICY_VIOLATION} "
        f"(RUNTIME_GATE_POLICY_VIOLATION), got {captured.get('exit_code')!r}"
    )
