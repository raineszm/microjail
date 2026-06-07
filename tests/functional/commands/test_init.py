from typing import TYPE_CHECKING

from typer.testing import CliRunner

from microjail.cli import app

if TYPE_CHECKING:
    from pytest_subprocess import FakeProcess


def test_init_delegates_to_workshop(fp: FakeProcess, project_name: str) -> None:
    fp.register(["workshop", "init", fp.any()], returncode=0)
    runner = CliRunner()
    result = runner.invoke(app, ["init", project_name])
    assert fp.call_count(["workshop", "init", fp.any()]) == 1
    assert result.exit_code == 0
