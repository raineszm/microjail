"""Fixtures and marks for the escape regression suite."""

import pytest

from tests.escape.fixtures import (  # noqa: F401
    escape_inputs,
    escape_preflight,
    escape_workspace,
)
from tests.marks import requires_lxd, requires_workshop

_LXD = requires_lxd()
_WORKSHOP = requires_workshop()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.slow)
        item.add_marker(_LXD)
        item.add_marker(_WORKSHOP)
