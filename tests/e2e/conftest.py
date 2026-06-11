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
    workshop.init(e2e_project.name, project=e2e_project.path)
    launch_with_retries(e2e_project.name, e2e_project.path)
    monkeypatch.chdir(e2e_project.path)
    yield e2e_project


@pytest.fixture
def e2e_workshop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A launched Workshop with fresh Microjail state per test."""
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        workshop.init(name, project=project)
        MicroJail(name=name, project_path=project, lockdown=Lockdown.default()).save()
        launch_with_retries(name, project)
        monkeypatch.chdir(project)
        yield SharedWorkshop(name=name, path=project)
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)


@pytest.fixture
def endpoint_e2e_workshop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A launched Workshop with fresh Microjail state for Endpoint capability e2e tests."""
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        workshop.init(name, project=project)
        MicroJail(name=name, project_path=project, lockdown=Lockdown.default()).save()
        launch_with_retries(name, project)
        monkeypatch.chdir(project)
        yield SharedWorkshop(name=name, path=project)
    finally:
        os.chdir(cwd)
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if {
            "e2e_project",
            "e2e_raw_workshop",
            "e2e_workshop",
            "endpoint_e2e_workshop",
        } & set(item.fixturenames):
            item.add_marker(pytest.mark.slow)
