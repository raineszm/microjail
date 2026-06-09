"""Fixtures for end-to-end tests — real Workshop, real CLI, no mocking."""

import os
import subprocess
import uuid
from pathlib import Path

import pytest

from microjail.adapters import workshop
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail
from tests._helpers import SharedWorkshop, launch_with_retries
from tests.marks import requires_lxd, requires_workshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
]


@pytest.fixture
def e2e_workshop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A launched workshop with a saved microjail config.

    Function-scoped: each test gets a fresh workshop. Tests that lock via CLI
    don't need to unlock — the workshop is destroyed at teardown.

    Gate state (``removed_devices``) is ephemeral and does not survive across
    CLI invocations, so function scope is necessary for correctness.
    """
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        workshop.init(name)

        mj = MicroJail(name=name, project_path=project, lockdown=Lockdown.default())
        mj.save()

        launch_with_retries(name, project)
        monkeypatch.chdir(project)
        yield SharedWorkshop(name=name, path=project)
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "e2e_workshop" in item.fixturenames:
            item.add_marker(pytest.mark.slow)
