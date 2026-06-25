"""Functional tests for the Warden running against a real LxdMonitor.

These tests use a real :class:`LxdMonitor` (not a fake) and a real
workload subprocess, but mock the :class:`MicroJail` layer where
Workshop interaction is not the focus. The goal is to catch regressions
in the supervision loop that only surface when a real ``LxdMonitor``
enforces its single-use contract on ``__iter__``.
"""

import subprocess
import uuid
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from microjail.microjail import MicroJail
from microjail.warden import Warden
from tests.marks import requires_lxd

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = [
    requires_lxd(),
    pytest.mark.slow,
]

IMAGE = "ubuntu:noble"
PROJECT = "default"
# Long enough for the pump thread to have started, called __iter__ on
# the real LxdMonitor, and been blocked in readline() for a full tick.
WORKLOAD_DURATION = "2"


@pytest.fixture
def ephemeral_container() -> Generator[tuple[str, str]]:
    """An ephemeral LXD container, started and stopped per test."""
    container = f"mj-warden-{uuid.uuid4().hex[:8]}"
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


def test_warden_supervise_does_not_reiterate_real_lxd_monitor(
    ephemeral_container: tuple[str, str],
) -> None:
    """Warden.supervise() must iterate the LxdMonitor exactly once.

    Regression test: the real ``LxdMonitor.__iter__`` raises
    ``RuntimeError("LxdMonitor is single-use")`` if called while a
    subprocess is already running. Earlier the supervision thread
    called ``iter(mon)`` explicitly and the pump thread also iterated
    the same monitor via its ``for event in mon:`` loop, causing a
    crash within the first interval of any workload that lived past
    the first tick.

    With the fix, the pump thread is the only one to call
    ``__iter__`` and the workload completes cleanly.
    """
    project, container = ephemeral_container

    mock_mj = Mock(spec=MicroJail)
    mock_mj.container_name.return_value = container
    mock_mj.lxd_project.return_value = project
    mock_mj.lockdown = Mock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []

    # Real workload process: long enough for the pump thread to be
    # blocked in readline() when the supervision thread wakes up
    # after the first interval (shortened to 0.5s below).
    workload = subprocess.Popen(
        ["sleep", WORKLOAD_DURATION],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    warden = Warden(mock_mj, workload, interval=0.5)

    try:
        exit_code = warden.supervise()
    finally:
        if workload.poll() is None:
            workload.kill()
            workload.wait()

    assert exit_code == 0, (
        f"workload exited with {exit_code}; "
        f"a non-zero exit here often indicates the Warden double-iterated "
        f"the LxdMonitor"
    )
