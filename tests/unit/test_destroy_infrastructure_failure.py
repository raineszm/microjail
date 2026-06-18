from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from microjail.adapters.workshop import Workshop
from microjail.cli import app
from microjail.lockdown import Lockdown
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def mock_microjail(tmp_path: Path):
    mj = MicroJail(
        workshop=Workshop(name="test-jail", project=tmp_path),
        lockdown=Lockdown.default(),
    )
    mj.save()
    (tmp_path / "data").mkdir()
    return mj


@patch.object(Workshop, "remove")
@patch.object(Workshop, "info")
def test_destroy_infrastructure_failure(
    mock_info, mock_remove, mock_microjail, tmp_path
):
    import subprocess

    mock_info.return_value = None
    mock_remove.side_effect = subprocess.CalledProcessError(1, "workshop")

    result = CliRunner().invoke(
        app, ["--project", str(tmp_path), "destroy"], catch_exceptions=False
    )

    assert result.exit_code == 1
    # Config and purge dir are preserved when teardown fails.
    assert MicroJail.load(tmp_path).name == "test-jail"
    assert (tmp_path / "data").exists()
