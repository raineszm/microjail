import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from microjail.adapters import workshop
from microjail.gates.network_drop import NetworkDrop
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail
from tests.marks import requires_lxd, requires_workshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
    pytest.mark.slow,
]


@dataclass(frozen=True)
class SharedWorkshop:
    name: str
    path: Path


LAUNCH_TIMEOUT = 30
LAUNCH_RETRIES = 2
LAUNCH_BACKOFF = 15
NETWORK_PROBE_TIMEOUT = 10


def launch_with_retries(name: str, project: Path):
    for attempt in range(LAUNCH_RETRIES + 1):
        try:
            workshop.launch(name, project=project, timeout=LAUNCH_TIMEOUT)
            return
        except subprocess.TimeoutExpired:
            if attempt == LAUNCH_RETRIES:
                raise
            time.sleep(LAUNCH_BACKOFF)


@pytest.fixture(scope="module")
def launched_workshop(tmp_path_factory):
    project = tmp_path_factory.mktemp("network-drop-workshop")
    name = f"mj-workshop-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        workshop.init(name)
        launch_with_retries(name, project)
        yield SharedWorkshop(name=name, path=project)
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)


def has_network_egress(workshop_state: SharedWorkshop) -> bool:
    result = workshop.exec_(
        workshop_state.name,
        workshop_state.path,
        [
            "python3",
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5).close()",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=NETWORK_PROBE_TIMEOUT,
    )
    return result.returncode == 0


def test_network_drop_blocks_egress_on_ensure_and_restores_it_on_release(
    launched_workshop: SharedWorkshop,
) -> None:
    if not has_network_egress(launched_workshop):
        pytest.skip("workshop does not have baseline network egress")

    lockdown = Lockdown(caps=[], gates=[NetworkDrop()])
    microjail = MicroJail(
        name=launched_workshop.name,
        project_path=launched_workshop.path,
        lockdown=lockdown,
    )

    try:
        lockdown.ensure(microjail)
        assert not has_network_egress(launched_workshop)
    finally:
        lockdown.release(microjail)

    assert has_network_egress(launched_workshop)
