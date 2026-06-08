"""Pytest configuration and shared fixtures."""

import uuid

import pytest


@pytest.fixture
def project_name():
    return f"mj-workshop-{uuid.uuid4().hex[:8]}"


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
