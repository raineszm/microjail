import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@dataclass(frozen=True)
class TmpWorkshop:
    name: str
    path: Path


@pytest.fixture
def tmp_workshop(tmpdir, project_name) -> Generator[TmpWorkshop]:
    """A tempory directory for creating a workshop.

    Ensure that the workshop is removed when it's done."""
    yield TmpWorkshop(
        name=project_name,
        path=tmpdir,
    )

    # Clean up the workshop before we move on.
    # Don't check the return code since its possible the workshop was never
    # launched
    subprocess.run(["workshop", "remove", "--project", tmpdir], check=False)
