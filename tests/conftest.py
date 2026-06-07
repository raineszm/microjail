"""Pytest configuration and shared fixtures."""

import uuid

import pytest


@pytest.fixture
def project_name():
    return f"mj-workshop-{uuid.uuid4().hex[:8]}"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-long",
        action="store_true",
        default=False,
        help="Include long-running tests (container creation, etc.).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_long = config.getoption("--run-long")

    skip_long = pytest.mark.skip(
        reason="long-running test skipped; pass --run-long to include"
    )

    for item in items:
        if not run_long and "long_running" in item.keywords:
            item.add_marker(skip_long)
