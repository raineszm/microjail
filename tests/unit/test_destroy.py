from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from microjail.adapters.workshop import Workshop, WorkshopInfo
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


@patch.object(Workshop, "info")
@patch.object(Workshop, "remove")
@patch("time.sleep")
def test_destroy_pending_workshop(
    mock_sleep, mock_remove, mock_info, mock_microjail, tmp_path
):
    mock_info.side_effect = [
        WorkshopInfo(name="test-jail", status="pending"),
        WorkshopInfo(name="test-jail", status="pending"),
        WorkshopInfo(name="test-jail", status="ready"),
    ]

    result = CliRunner().invoke(app, ["--project", str(tmp_path), "destroy"])

    assert result.exit_code == 0
    assert mock_info.call_count == 3
    assert mock_sleep.call_count == 2
    mock_remove.assert_called_once_with()


@patch.object(Workshop, "info")
@patch.object(Workshop, "start")
@patch.object(Workshop, "remove")
def test_destroy_off_workshop(
    mock_remove, mock_start, mock_info, mock_microjail, tmp_path
):
    mock_info.return_value = WorkshopInfo(name="test-jail", status="off")

    result = CliRunner().invoke(app, ["--project", str(tmp_path), "destroy"])

    assert result.exit_code == 0
    mock_start.assert_called_once_with()
    mock_remove.assert_called_once_with()
