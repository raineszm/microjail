from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from microjail.adapters import workshop
from microjail.cli import app
from microjail.gates.network_drop import NetworkDrop
from microjail.gates.readonly_config import ReadonlyConfig
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from pathlib import Path


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_delegates_to_workshop_and_writes_config(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name])

    mock_init.assert_called_once_with(
        project_name, project=tmp_path, sdks=None, base=None
    )
    assert result.exit_code == 0
    loaded = MicroJail.load(tmp_path)
    assert loaded.name == project_name
    assert loaded.project_path == tmp_path
    assert loaded.lockdown.caps == []
    assert [type(gate) for gate in loaded.lockdown.gates] == [
        NetworkDrop,
        ReadonlyConfig,
    ]


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_bails_if_exists(
    mock_init: AsyncMock, tmp_path: Path, monkeypatch, project_name: str
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_init.side_effect = workshop.WorkshopExistsError(
        name=project_name, project=tmp_path
    )

    result = CliRunner().invoke(app, ["init", project_name])

    mock_init.assert_called_once_with(
        project_name, project=tmp_path, sdks=None, base=None
    )
    assert result.exit_code == 1
    assert "already exists" in result.stderr
    assert "--overwrite" in result.stderr
    assert "--adopt" in result.stderr
    assert not (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_workshop_failure_exits_nonzero_without_config(
    mock_init: AsyncMock, tmp_path: Path, monkeypatch, project_name: str
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_init.side_effect = RuntimeError("workshop unavailable")

    result = CliRunner().invoke(app, ["init", project_name])

    assert result.exit_code == 1
    assert "Failed to initialize Workshop" in result.stderr
    assert "workshop unavailable" in result.stderr
    assert not (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.exists", new_callable=AsyncMock)
def test_init_adopt_fails_if_doesnt_exist(
    mock_exists: AsyncMock, tmp_path: Path, monkeypatch
) -> None:
    mock_exists.return_value = False
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "bad-name", "--adopt"])

    mock_exists.assert_called_once_with("bad-name", tmp_path)
    assert result.exit_code == 1
    assert "does not exist" in result.stderr
    assert not (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_overwrite_warns_if_doesnt_exist(
    mock_init: AsyncMock, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", "bad-name", "--overwrite"])

    mock_init.assert_called_once_with(
        "bad-name", project=tmp_path, sdks=None, base=None
    )
    assert result.exit_code == 0
    assert "does not exist" in result.stderr
    assert MicroJail.load(tmp_path).name == "bad-name"


@patch("microjail.adapters.workshop.exists", new_callable=AsyncMock)
def test_init_adopt_succeeds_if_exists(
    mock_exists: AsyncMock, tmp_path: Path, monkeypatch, project_name: str
) -> None:
    mock_exists.return_value = True
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name, "--adopt"])

    mock_exists.assert_called_once_with(project_name, tmp_path)
    assert result.exit_code == 0
    assert "Adopted" in result.stdout
    loaded = MicroJail.load(tmp_path)
    assert loaded.name == project_name
    assert loaded.project_path == tmp_path


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_delegates_to_workshop_with_default_sdks(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name])

    assert result.exit_code == 0
    mock_init.assert_called_once_with(
        project_name, project=tmp_path, sdks=None, base=None
    )
    loaded = MicroJail.load(tmp_path)
    assert loaded.name == project_name


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_default_omits_base(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name])

    assert result.exit_code == 0
    _, kwargs = mock_init.call_args
    assert kwargs.get("base") is None
    assert kwargs.get("sdks") is None


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_forwards_single_sdk(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name, "--sdks", "golang"])

    assert result.exit_code == 0
    mock_init.assert_called_once_with(
        project_name, project=tmp_path, sdks=["golang"], base=None
    )


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_forwards_multiple_sdks(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name, "--sdks", "golang,java"])

    assert result.exit_code == 0
    mock_init.assert_called_once_with(
        project_name, project=tmp_path, sdks=["golang", "java"], base=None
    )


@patch("microjail.adapters.workshop.anyio.run_process", new_callable=AsyncMock)
def test_init_preserves_direnv_in_sdk_list(
    mock_run: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_run.return_value = MagicMock()
    mock_run.return_value.stdout = b""

    result = CliRunner().invoke(app, ["init", project_name, "--sdks", "golang"])

    assert result.exit_code == 0
    args, _ = mock_run.call_args
    assert "--sdks" in args[0]
    sdks_idx = args[0].index("--sdks")
    sdks_value = args[0][sdks_idx + 1]
    sdks_list = sdks_value.split(",")
    assert "golang" in sdks_list
    assert "direnv" in sdks_list


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_forwards_sdks_to_adapter(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name, "--sdks", "golang"])

    assert result.exit_code == 0
    _, kwargs = mock_init.call_args
    assert kwargs["sdks"] == ["golang"]


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_forwards_base(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name, "--base", "ubuntu@22.04"])

    assert result.exit_code == 0
    mock_init.assert_called_once_with(
        project_name, project=tmp_path, sdks=None, base="ubuntu@22.04"
    )


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_forwards_base_to_adapter(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name, "--base", "ubuntu@22.04"])

    assert result.exit_code == 0
    _, kwargs = mock_init.call_args
    assert kwargs["base"] == "ubuntu@22.04"


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_omits_base_when_not_provided(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name])

    assert result.exit_code == 0
    _, kwargs = mock_init.call_args
    assert kwargs["base"] is None


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_init_exits_nonzero_on_sdk_failure(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    mock_init.side_effect = RuntimeError("invalid SDK")

    result = CliRunner().invoke(
        app, ["init", project_name, "--sdks", "invalid-sdk-name"]
    )

    assert result.exit_code != 0
    assert "Failed to initialize Workshop" in result.stderr
    assert not (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.exists", new_callable=AsyncMock)
@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_adopt_ignores_sdks(
    mock_init: AsyncMock,
    mock_exists: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    mock_exists.return_value = True
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app, ["init", project_name, "--adopt", "--sdks", "golang"]
    )

    assert result.exit_code == 0
    mock_init.assert_not_called()
    assert MicroJail.load(tmp_path).name == project_name


@patch("microjail.adapters.workshop.exists", new_callable=AsyncMock)
@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_adopt_warns_on_base(
    mock_init: AsyncMock,
    mock_exists: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    mock_exists.return_value = True
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app, ["init", project_name, "--adopt", "--base", "ubuntu@22.04"]
    )

    assert result.exit_code == 0
    assert "--base is ignored during adopt" in result.stderr
    mock_init.assert_not_called()
    assert MicroJail.load(tmp_path).name == project_name


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_overwrite_forwards_sdks_and_base(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    workshop_dir = tmp_path / ".workshop"
    workshop_dir.mkdir()
    (workshop_dir / f"{project_name}.yaml").touch()

    result = CliRunner().invoke(
        app,
        [
            "init",
            project_name,
            "--overwrite",
            "--sdks",
            "golang",
            "--base",
            "ubuntu@22.04",
        ],
    )

    assert result.exit_code == 0
    mock_init.assert_called_once_with(
        project_name, project=tmp_path, sdks=["golang"], base="ubuntu@22.04"
    )
    assert (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_project_flag_resolves_relative_to_absolute(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    other = tmp_path / "other"
    other.mkdir()

    result = CliRunner().invoke(app, ["--project", str(other), "init", project_name])

    assert result.exit_code == 0
    assert (other / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_project_flag_accepts_absolute_path(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir("/")
    proj = tmp_path / "myproject"
    proj.mkdir(parents=True)

    result = CliRunner().invoke(app, ["--project", str(proj), "init", project_name])

    assert result.exit_code == 0
    assert (proj / ".microjail" / "config.yaml").exists()


@patch("microjail.adapters.workshop.init", new_callable=AsyncMock)
def test_project_flag_defaults_to_cwd(
    mock_init: AsyncMock,
    tmp_path: Path,
    monkeypatch,
    project_name: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["init", project_name])

    assert result.exit_code == 0
    assert (tmp_path / ".microjail" / "config.yaml").exists()


@patch("microjail.microjail.MicroJail.ensure", new_callable=AsyncMock)
def test_lock_loads_config_from_resolved_project_path(
    mock_ensure: AsyncMock,
    tmp_path: Path,
    monkeypatch,
) -> None:
    proj = tmp_path / "myproject"
    proj.mkdir(parents=True)
    microjail_config = proj / ".microjail" / "config.yaml"
    microjail_config.parent.mkdir()
    microjail_config.write_text(
        f"name: test-jail\nproject_path: {proj}\nlockdown:\n  caps: []\n  gates: []\n",
        encoding="utf-8",
    )
    monkeypatch.chdir("/")

    result = CliRunner().invoke(app, ["--project", str(proj), "lock"])

    assert result.exit_code == 0
    mock_ensure.assert_called_once()


@patch("microjail.microjail.MicroJail.release", new_callable=AsyncMock)
@patch("microjail.microjail.MicroJail.load")
def test_unlock_loads_config_from_resolved_project_path(
    mock_load: MagicMock,
    mock_release: AsyncMock,
    tmp_path: Path,
    monkeypatch,
) -> None:
    proj = tmp_path / "myproject"
    proj.mkdir(parents=True)
    monkeypatch.chdir("/")

    mock_mj = MagicMock(spec=MicroJail)
    mock_mj.release = mock_release
    mock_mj.lockdown = MagicMock()
    mock_mj.lockdown.gates = []
    mock_mj.lockdown.caps = []
    mock_load.return_value = mock_mj

    result = CliRunner().invoke(app, ["--project", str(proj), "unlock"])

    assert result.exit_code == 0
    mock_load.assert_called_once_with(proj)
