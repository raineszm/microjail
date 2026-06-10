"""Fixtures for end-to-end tests — real Workshop, real CLI, no mocking."""

import os
import shutil
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
def e2e_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A fresh project path/name pair with Workshop teardown."""
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        monkeypatch.chdir(project)
        yield SharedWorkshop(name=name, path=project)
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)


@pytest.fixture
def e2e_raw_workshop(e2e_project: SharedWorkshop, monkeypatch: pytest.MonkeyPatch):
    """A launched Workshop without a Microjail config."""
    workshop.init(e2e_project.name)
    launch_with_retries(e2e_project.name, e2e_project.path)
    monkeypatch.chdir(e2e_project.path)
    yield e2e_project


def create_launched_workshop(
    tmp_path_factory: pytest.TempPathFactory,
    basename: str,
) -> SharedWorkshop:
    project = tmp_path_factory.mktemp(basename)
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    os.chdir(project)
    workshop.init(name)
    MicroJail(name=name, project_path=project, lockdown=Lockdown.default()).save()
    launch_with_retries(name, project)
    return SharedWorkshop(name=name, path=project)


@pytest.fixture(scope="session")
def reusable_e2e_workshop(tmp_path_factory: pytest.TempPathFactory):
    """One launched Workshop reused by default-policy e2e tests."""
    cwd = Path.cwd()
    try:
        ws = create_launched_workshop(tmp_path_factory, "workshop-reused")
        yield ws
    finally:
        os.chdir(cwd)
        if "ws" in locals():
            subprocess.run(
                ["workshop", "remove", "--project", str(ws.path)],
                check=False,
            )


@pytest.fixture(scope="session")
def reusable_endpoint_workshop(tmp_path_factory: pytest.TempPathFactory):
    """One launched Workshop reused by Endpoint capability e2e tests."""
    cwd = Path.cwd()
    try:
        ws = create_launched_workshop(tmp_path_factory, "workshop-endpoint")
        yield ws
    finally:
        os.chdir(cwd)
        if "ws" in locals():
            subprocess.run(
                ["workshop", "remove", "--project", str(ws.path)],
                check=False,
            )


def reset_reusable_workshop(ws: SharedWorkshop) -> None:
    """Reset policy/config/file state for a reusable launched Workshop."""
    workshop.restore(ws.name, ws.path)
    reset_project_files(ws)


def reset_project_files(ws: SharedWorkshop) -> None:
    shutil.rmtree(ws.path / ".microjail", ignore_errors=True)
    for filename in ("input.txt", "out.txt", "endpoint-ok", "started"):
        path = ws.path / filename
        if path.exists():
            path.unlink()

    MicroJail(name=ws.name, project_path=ws.path, lockdown=Lockdown.default()).save()


@pytest.fixture
def e2e_workshop(
    reusable_e2e_workshop: SharedWorkshop,
    monkeypatch: pytest.MonkeyPatch,
):
    """A launched Workshop with reset Microjail state."""
    reset_reusable_workshop(reusable_e2e_workshop)
    monkeypatch.chdir(reusable_e2e_workshop.path)
    yield reusable_e2e_workshop
    reset_reusable_workshop(reusable_e2e_workshop)


@pytest.fixture
def endpoint_e2e_workshop(
    reusable_endpoint_workshop: SharedWorkshop,
    monkeypatch: pytest.MonkeyPatch,
):
    """A launched Workshop isolated for Endpoint capability e2e tests."""
    reset_reusable_workshop(reusable_endpoint_workshop)
    monkeypatch.chdir(reusable_endpoint_workshop.path)
    yield reusable_endpoint_workshop
    reset_reusable_workshop(reusable_endpoint_workshop)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if {
            "e2e_project",
            "e2e_raw_workshop",
            "e2e_workshop",
            "endpoint_e2e_workshop",
        } & set(item.fixturenames):
            item.add_marker(pytest.mark.slow)
