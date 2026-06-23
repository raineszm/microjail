"""Functional tests for :class:`microjail.adapters.lxd_monitor.LxdMonitor`.

These tests exercise :class:`LxdMonitor` against a real LXD daemon. They do
**not** go through Workshop or Microjail — the monitor is a library that wraps
``lxc monitor`` and only needs a real LXD project and a real container.
"""

import queue
import subprocess
import threading
import uuid
from typing import TYPE_CHECKING

import pytest

from microjail.adapters.lxd_monitor import LifecycleEvent, LxdMonitor
from tests.marks import requires_lxd

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = [
    requires_lxd(),
    pytest.mark.slow,
]
TEST_DEVICE = "eth1"
EVENT_TIMEOUT = 60.0
IMAGE = "ubuntu:noble"
PROJECT = "default"


class EventCollector:
    """Run an :class:`LxdMonitor` on a worker thread and expose events via a
    timeout-bounded :meth:`wait_for_action` method.
    """

    def __init__(self, monitor: LxdMonitor) -> None:
        self.monitor = monitor
        self.events: queue.Queue[LifecycleEvent] = queue.Queue()
        self.stop_event = threading.Event()
        self.collected: list[LifecycleEvent] = []

    def collect_events(self) -> None:
        for event in self.monitor:
            if self.stop_event.is_set():
                return
            self.events.put(event)

    def start(self) -> None:
        self.worker_thread = threading.Thread(
            target=self.collect_events, name="lxd-monitor-collect"
        )
        self.worker_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.monitor.close()
        self.worker_thread.join(timeout=2.0)

    def __enter__(self) -> EventCollector:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def wait_for_action(
        self, action: str, timeout: float = EVENT_TIMEOUT
    ) -> LifecycleEvent:
        """Return the first event whose ``metadata.action`` matches *action*."""
        deadline = threading.Event()
        timer = threading.Timer(timeout, deadline.set)
        timer.start()
        try:
            while not deadline.is_set():
                try:
                    event = self.events.get(timeout=0.1)
                except queue.Empty:
                    continue
                self.collected.append(event)
                if event.metadata.action == action:
                    return event
            raise AssertionError(
                f"Timed out after {timeout}s waiting for action={action!r}; "
                f"collected so far: {[e.metadata.action for e in self.collected]}"
            )
        finally:
            timer.cancel()


@pytest.fixture
def ephemeral_container() -> Generator[tuple[str, str]]:
    container = f"mj-lxdmon-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["lxc", "init", IMAGE, container, "--ephemeral", "--project", PROJECT],
        check=True,
        capture_output=True,
    )
    yield PROJECT, container

    subprocess.run(
        ["lxc", "stop", container, "--project", PROJECT],
        check=False,
        capture_output=True,
    )


def test_lxd_monitor_observes_instance_started_event(
    ephemeral_container: tuple[str, str],
) -> None:
    project, container = ephemeral_container
    monitor = LxdMonitor(container_name=container, lxd_project=project)

    with EventCollector(monitor) as collector:
        subprocess.run(
            ["lxc", "start", container, "--project", project],
            check=True,
            capture_output=True,
        )

        event = collector.wait_for_action("instance-started")

    assert event.project == project
    assert event.metadata.source == f"/1.0/instances/{container}"


def test_lxd_monitor_observes_config_device_changes(
    ephemeral_container: tuple[str, str],
) -> None:
    project, container = ephemeral_container
    monitor = LxdMonitor(container_name=container, lxd_project=project)

    with EventCollector(monitor) as collector:
        subprocess.run(
            ["lxc", "start", container, "--project", project],
            check=True,
            capture_output=True,
        )
        # ``nictype=p2p`` avoids a conflict with the default profile's ``eth0``,
        # which is bridged to ``lxdbr0``; a second bridged device on the same
        # managed network is rejected with an "Instance DNS name conflict" error.
        subprocess.run(
            [
                "lxc",
                "config",
                "device",
                "add",
                container,
                TEST_DEVICE,
                "nic",
                "nictype=p2p",
                "--project",
                project,
            ],
            check=True,
            capture_output=True,
        )
        added = collector.wait_for_action("instance-updated")

        subprocess.run(
            [
                "lxc",
                "config",
                "device",
                "remove",
                container,
                TEST_DEVICE,
                "--project",
                project,
            ],
            check=True,
            capture_output=True,
        )
        removed = collector.wait_for_action("instance-updated")

    assert added.project == project
    assert added.metadata.source == f"/1.0/instances/{container}"
    assert removed.project == project
    assert removed.metadata.source == f"/1.0/instances/{container}"
