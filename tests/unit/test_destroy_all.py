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
def test_destroy_all_interactive_yes(mock_info, mock_remove, mock_microjail, tmp_path):
    mock_info.return_value = None  # Workshop is already removed or doesn't exist

    result = CliRunner().invoke(
        app, ["--project", str(tmp_path), "destroy", "--all"], input="y\n"
    )

    assert result.exit_code == 0
    assert not tmp_path.exists()


@patch.object(Workshop, "remove")
@patch.object(Workshop, "info")
def test_destroy_all_interactive_no(mock_info, mock_remove, mock_microjail, tmp_path):
    result = CliRunner().invoke(
        app, ["--project", str(tmp_path), "destroy", "--all"], input="n\n"
    )
    assert result.exit_code == 1  # aborts
    assert tmp_path.exists()  # project is kept


@patch.object(Workshop, "remove")
@patch.object(Workshop, "info")
def test_destroy_all_bypass(mock_info, mock_remove, mock_microjail, tmp_path):
    mock_info.return_value = None

    result = CliRunner().invoke(
        app, ["--project", str(tmp_path), "destroy", "--all", "--yes-i-really-mean-it"]
    )

    assert result.exit_code == 0
    assert not tmp_path.exists()
