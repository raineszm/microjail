from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from microjail.adapters import workshop
from microjail.cli import app


@patch("microjail.adapters.workshop.init")
def test_init_delegates_to_workshop(mock_init: MagicMock, project_name: str) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init", project_name])
    mock_init.assert_called_once_with(project_name)
    assert result.exit_code == 0


@patch("microjail.adapters.workshop.init")
def test_init_bails_if_exists(mock_init: MagicMock, project_name: str) -> None:
    mock_init.side_effect = workshop.WorkshopExistsError(
        name=project_name, project=Path.cwd()
    )
    runner = CliRunner()
    result = runner.invoke(app, ["init", project_name])
    mock_init.assert_called_once_with(project_name)
    assert result.exit_code == 1
    assert "already exists" in result.stderr
    assert "--modify" in result.stderr
    assert "--adopt" in result.stderr


@patch("microjail.adapters.workshop.exists", return_value=False)
def test_init_adopt_fails_if_doesnt_exist(mock_exists: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init", "bad-name", "--adopt"])
    assert result.exit_code == 1
    assert "does not exist" in result.stderr


@patch("microjail.adapters.workshop.init")
def test_init_overwrite_warns_if_doesnt_exist(mock_init: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init", "bad-name", "--overwrite"])
    assert result.exit_code == 0
    assert "does not exist" in result.stderr


@patch("microjail.adapters.workshop.exists", return_value=True)
def test_init_adopt_succeeds_if_exists(
    mock_exists: MagicMock, project_name: str
) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init", project_name, "--adopt"])
    mock_exists.assert_called_once()
    assert result.exit_code == 0
    assert "Adopted" in result.stdout
