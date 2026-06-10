from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from microjail.adapters import workshop
from microjail.cli import app
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


@patch("microjail.adapters.workshop.init")
def test_init_delegates_to_workshop_and_writes_config(
    mock_init: MagicMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name])

    mock_init.assert_called_once_with(project_name)
    assert result.exit_code == 0
    loaded = MicroJail.load(tmp_path)
    assert loaded.name == project_name
    assert loaded.project_path == tmp_path
    assert loaded.lockdown.caps == []
    assert [type(gate) for gate in loaded.lockdown.gates] == [
        NetworkDrop,
        ReadonlyConfig,
    ]


@patch("microjail.adapters.workshop.init")
def test_init_bails_if_exists(
    mock_init: MagicMock, tmp_path: Path, monkeypatch, project_name: str
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_init.side_effect = workshop.WorkshopExistsError(
        name=project_name, project=tmp_path
    )

    result = CliRunner().invoke(app, ["init", project_name])

    mock_init.assert_called_once_with(project_name)
    assert result.exit_code == 1
    assert "already exists" in result.stderr
    assert "--overwrite" in result.stderr
    assert "--adopt" in result.stderr
    assert not (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.init")
def test_init_workshop_failure_exits_nonzero_without_config(
    mock_init: MagicMock, tmp_path: Path, monkeypatch, project_name: str
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_init.side_effect = RuntimeError("workshop unavailable")

    result = CliRunner().invoke(app, ["init", project_name])

    assert result.exit_code == 1
    assert "Failed to initialize Workshop" in result.stderr
    assert "workshop unavailable" in result.stderr
    assert not (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.exists", return_value=False)
def test_init_adopt_fails_if_doesnt_exist(
    mock_exists: MagicMock, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "bad-name", "--adopt"])

    mock_exists.assert_called_once_with("bad-name", tmp_path)
    assert result.exit_code == 1
    assert "does not exist" in result.stderr
    assert not (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.init")
def test_init_overwrite_warns_if_doesnt_exist(
    mock_init: MagicMock, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "bad-name", "--overwrite"])

    mock_init.assert_called_once_with("bad-name")
    assert result.exit_code == 0
    assert "does not exist" in result.stderr
    assert MicroJail.load(tmp_path).name == "bad-name"


@patch("microjail.adapters.workshop.exists", return_value=True)
def test_init_adopt_succeeds_if_exists(
    mock_exists: MagicMock, tmp_path: Path, monkeypatch, project_name: str
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name, "--adopt"])

    mock_exists.assert_called_once_with(project_name, tmp_path)
    assert result.exit_code == 0
    assert "Adopted" in result.stdout
    loaded = MicroJail.load(tmp_path)
    assert loaded.name == project_name
    assert loaded.project_path == tmp_path
