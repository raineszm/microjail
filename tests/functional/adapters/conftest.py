import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from microjail.adapters.workshop import Workshop


@pytest.fixture
def tmp_workshop(tmp_path, project_name, monkeypatch) -> Generator[Workshop]:
    """A temporary directory for creating a workshop.

    Ensure that the workshop is removed when it's done."""

    monkeypatch.chdir(tmp_path)

    yield Workshop(
        name=project_name,
        project=tmp_path,
    )

    # Clean up the workshop before we move on.
    # Don't check the return code since its possible the workshop was never
    # launched
    subprocess.run(["workshop", "remove", "--project", str(tmp_path)], check=False)


def pytest_collection_modifyitems(items):
    for item in items:
        # Launching a workshop is slow, so mark it as such
        if "launched_workshop" in item.fixturenames:
            item.add_marker(pytest.mark.slow)
