"""Pytest configuration and shared fixtures."""

import uuid
from pathlib import Path  # noqa: TC003

import pytest


@pytest.fixture
def project_name():
    return f"mj-workshop-{uuid.uuid4().hex[:8]}"


def create_microjail_config(project: Path) -> Path:
    """Create a minimal .microjail/config.yaml in *project*."""
    config = project / ".microjail" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        f"name: test-jail\nproject_path: {project}\nlockdown:\n  caps: []\n  gates: []\n",
        encoding="utf-8",
    )
    return config


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

    for item in items:
        if not run_slow and item.get_closest_marker("slow"):
            item.add_marker(skip_long)
