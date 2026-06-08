from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from microjail.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_subprocess import FakeProcess


def _init_already_exists(name: str, path: Path) -> str:
    return f'error: cannot init: "{name}" workshop already exists at "{path}"'


@dataclass
class ExistingWorkshop:
    name: str
    path: Path


@pytest.fixture
def fp_existing_workshop(
    fp: FakeProcess, project_name: str, tmp_path: Path
) -> ExistingWorkshop:
    fp.register(
        ["workshop", "init", project_name, fp.any()],
        returncode=1,
        stderr=_init_already_exists(
            project_name, tmp_path / ".workshop" / f"{project_name}.yaml"
        ),
    )
    fp.register(
        ["workshop", "init", fp.any()],
        returncode=0,
    )
    fp.register(
        ["workshop", "list", fp.any()], returncode=0, stdout=f"{project_name}  Ready  -"
    )

    workshop_dir = tmp_path / ".workshop"
    workshop_dir.mkdir()
    (workshop_dir / f"{project_name}.yaml").touch()
    return ExistingWorkshop(name=project_name, path=tmp_path)


def test_init_delegates_to_workshop(fp: FakeProcess, project_name: str) -> None:
    fp.register(["workshop", "init", fp.any()], returncode=0)
    runner = CliRunner()
    result = runner.invoke(app, ["init", project_name])
    assert fp.call_count(["workshop", "init", fp.any()]) == 1
    assert result.exit_code == 0


def test_init_bails_if_exists(
    fp: FakeProcess, fp_existing_workshop: ExistingWorkshop
) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init", fp_existing_workshop.name])
    assert fp.call_count(["workshop", "init", fp.any()]) == 1
    assert result.exit_code == 1
    assert "already exists" in result.stderr
    assert "--modify" in result.stderr
    assert "--adopt" in result.stderr


def test_init_adopt_fails_if_doesnt_exist(
    fp: FakeProcess, fp_existing_workshop: ExistingWorkshop
) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init", "bad-name", "--adopt"])
    assert result.exit_code == 1
    assert "does not exist" in result.stderr


def test_init_overwrite_warns_if_doesnt_exist(
    fp: FakeProcess, fp_existing_workshop: ExistingWorkshop
) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init", "bad-name", "--overwrite"])
    assert result.exit_code == 0
    assert "does not exist" in result.stderr


def test_init_adopt_succeeds_if_exists(
    fp: FakeProcess, fp_existing_workshop: ExistingWorkshop
) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["init", fp_existing_workshop.name, "--adopt"])
    assert fp.call_count(["workshop", "list", fp.any()]) > 0
    assert result.exit_code == 0
    assert "Adopted" in result.stdout
