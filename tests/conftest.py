"""Pytest configuration and shared fixtures."""

import shutil
import uuid
from pathlib import Path  # noqa: TC003

import pytest


@pytest.fixture
def project_name():
    return f"mj-workshop-{uuid.uuid4().hex[:8]}"


def create_microjail_config(project: Path) -> Path:
    """Create a .microjail/config.yaml in *project* matching what ``microjail init`` writes."""
    from microjail.adapters.workshop import Workshop
    from microjail.lockdown import Lockdown
    from microjail.microjail import MicroJail

    config = MicroJail(
        workshop=Workshop(name="test-jail", project=project),
        lockdown=Lockdown.default(),
    )
    config.save()
    if config.purge_path:
        (project / config.purge_path).mkdir(parents=True, exist_ok=True)
    return config.config_path


@pytest.fixture
def microjail_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary directory with a microjail config, set as cwd."""
    create_microjail_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Include slow tests (container creation, etc.).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_slow = config.getoption("--slow")
    skip_long = pytest.mark.skip(reason="slow test skipped; pass --slow to include")
    skip_lxc = pytest.mark.skip(reason="lxc not installed")
    skip_workshop = pytest.mark.skip(reason="workshop not installed")
    has_lxc = shutil.which("lxc") is not None
    has_workshop = shutil.which("workshop") is not None
    for item in items:
        if not run_slow and item.get_closest_marker("slow"):
            item.add_marker(skip_long)
        if not has_lxc and item.get_closest_marker("lxd"):
            item.add_marker(skip_lxc)
        if not has_workshop and item.get_closest_marker("workshop"):
            item.add_marker(skip_workshop)
