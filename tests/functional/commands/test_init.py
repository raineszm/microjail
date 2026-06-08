from typing import TYPE_CHECKING

from typer.testing import CliRunner

from microjail.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_subprocess import FakeProcess


def _init_already_exists(name: str, path: Path) -> str:
    return f'error: cannot init: "{name}" workshop already exists at "{path}"'


def test_init_delegates_to_workshop(fp: FakeProcess, project_name: str) -> None:
    fp.register(["workshop", "init", fp.any()], returncode=0)
    runner = CliRunner()
    result = runner.invoke(app, ["init", project_name])
    assert fp.call_count(["workshop", "init", fp.any()]) == 1
    assert result.exit_code == 0


def test_init_bails_if_exists(
    fp: FakeProcess, project_name: str, tmp_path: Path
) -> None:
    fp.register(
        ["workshop", "init", fp.any()],
        returncode=1,
        stderr=_init_already_exists(
            project_name, tmp_path / ".workshop" / f"{project_name}.yaml"
        ),
    )
    runner = CliRunner()
    result = runner.invoke(app, ["init", project_name])
    assert fp.call_count(["workshop", "init", fp.any()]) == 1
    assert result.exit_code == 1
    assert "already exists" in result.stderr
    assert "--modify" in result.stderr
    assert "--adopt" in result.stderr
