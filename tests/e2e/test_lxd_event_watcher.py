"""End-to-end tests for the LXD event watcher against a real LXD daemon.

These tests run ``microjail exec`` via :class:`typer.testing.CliRunner` in
a thread so a real LXD action can be interleaved with the workload while
the watcher's WebSocket is live. The ``CliRunner`` invokes the CLI in
process; nothing here shells out to a ``microjail`` binary.
"""

import threading
import time
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from microjail import policy
from microjail.adapters.lxc import add_device
from microjail.cli import app

if TYPE_CHECKING:
    from microjail.adapters.workshop import Workshop


WORKLOAD_READY_TIMEOUT = 15.0
WORKLOAD_RUN_TIMEOUT = 20.0
WORKLOAD_POLL_INTERVAL = 0.1


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
