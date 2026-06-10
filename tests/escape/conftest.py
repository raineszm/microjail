"""Fixtures and markers for CTF escape tests.

Escape tests exercise container-breakout scenarios against real LXD
containers launched by Workshop, so they are gated on both ``lxc`` and
``workshop`` being available and are always marked ``slow``.
"""

from pathlib import Path

import pytest

from tests.marks import requires_lxd, requires_workshop


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply lxd, workshop, and slow markers to all escape tests."""
    escape_dir = Path(__file__).parent.resolve()

    for item in items:
        # Only apply to tests in the escape directory
        if not Path(item.path).resolve().is_relative_to(escape_dir):
            continue

        item.add_marker(requires_lxd())
        item.add_marker(requires_workshop())
        item.add_marker(pytest.mark.slow)
