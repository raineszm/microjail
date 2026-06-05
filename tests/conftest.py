"""Pytest configuration and shared fixtures."""

import shutil
import subprocess

import pytest


def _lxd_available() -> bool:
    """Return True if lxc is on PATH and the LXD daemon responds."""
    if shutil.which("lxc") is None:
        return False
    return (
        subprocess.run(["lxc", "version"], capture_output=True, check=False).returncode
        == 0
    )


def _workshop_available() -> bool:
    """Return True if the workshop binary is on PATH."""
    return shutil.which("workshop") is not None


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
    lxd_ok = _lxd_available()
    workshop_ok = _workshop_available()
    run_long = config.getoption("--run-long")

    skip_lxd = pytest.mark.skip(
        reason="LXD daemon unavailable (lxc not found or unresponsive)"
    )
    skip_workshop = pytest.mark.skip(
        reason="workshop CLI unavailable (workshop not found on PATH)"
    )
    skip_long = pytest.mark.skip(
        reason="long-running test skipped; pass --run-long to include"
    )

    for item in items:
        if not lxd_ok and "lxd" in item.keywords:
            item.add_marker(skip_lxd)
        if not workshop_ok and "workshop" in item.keywords:
            item.add_marker(skip_workshop)
        if not run_long and "long_running" in item.keywords:
            item.add_marker(skip_long)
