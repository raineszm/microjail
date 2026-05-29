"""Pytest configuration and shared fixtures."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--lxd",
        action="store_true",
        default=False,
        help="Run tests that require a live LXD / Workshop installation.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--lxd"):
        return
    skip_lxd = pytest.mark.skip(reason="requires LXD/Workshop — pass --lxd to run")
    for item in items:
        if item.get_closest_marker("lxd"):
            item.add_marker(skip_lxd)
