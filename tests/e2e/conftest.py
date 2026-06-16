"""Fixtures for end-to-end tests — real Workshop, real CLI, no mocking."""

import os
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from microjail.adapters.workshop import Workshop
from microjail.microjail import MicroJail
from tests.marks import requires_lxd, requires_workshop

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = [
    requires_lxd(),
    requires_workshop(),
]


def clean_up_project(project: Path, name: str) -> None:
    try:
        MicroJail.load(project).destroy()
    except Exception:
        subprocess.run(["workshop", "remove", "--project", str(project)], check=False)


@pytest.fixture
def e2e_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Workshop]:
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        monkeypatch.chdir(project)
        yield Workshop(name=name, project=project)
    finally:
        os.chdir(cwd)
        clean_up_project(project, name)


@pytest.fixture
def e2e_raw_workshop(
    e2e_project: Workshop, monkeypatch: pytest.MonkeyPatch
) -> Generator[Workshop]:
    """A launched Workshop without a Microjail config."""
    e2e_project.init(e2e_project.name, project=e2e_project.project)
    e2e_project.launch()
    monkeypatch.chdir(e2e_project.project)
    yield e2e_project


@pytest.fixture
def e2e_workshop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Workshop]:
    """A launched Workshop with fresh Microjail state per test."""
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        MicroJail.init(name, project_path=project)
        ws = Workshop(name=name, project=project)
        ws.launch()
        monkeypatch.chdir(project)
        yield ws
    finally:
        os.chdir(cwd)
        clean_up_project(project, name)


@pytest.fixture
def e2e_unlaunched_workshop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Workshop]:
    """An unlaunched Workshop with fresh Microjail state per test."""
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        MicroJail.init(name, project_path=project)
        monkeypatch.chdir(project)
        yield Workshop(name=name, project=project)
    finally:
        os.chdir(cwd)
        clean_up_project(project, name)


@pytest.fixture
def endpoint_e2e_workshop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Workshop]:
    """A launched Workshop with fresh Microjail state for Endpoint capability e2e tests."""
    project = tmp_path / "workshop"
    project.mkdir()
    name = f"mj-e2e-{uuid.uuid4().hex[:8]}"
    cwd = Path.cwd()

    try:
        os.chdir(project)
        MicroJail.init(name, project_path=project)
        ws = Workshop(name=name, project=project)
        ws.launch()
        monkeypatch.chdir(project)
        yield ws
    finally:
        os.chdir(cwd)
        clean_up_project(project, name)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        fixturenames = getattr(item, "fixturenames", None)
        if fixturenames and {
            "e2e_project",
            "e2e_raw_workshop",
            "e2e_workshop",
            "endpoint_e2e_workshop",
        } & set(fixturenames):
            item.add_marker(pytest.mark.slow)
