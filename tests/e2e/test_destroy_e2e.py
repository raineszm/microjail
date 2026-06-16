from typing import TYPE_CHECKING

from typer.testing import CliRunner

from microjail.cli import app
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from microjail.adapters.workshop import Workshop


def test_destroy_default_behavior(e2e_project: Workshop) -> None:
    # Arrange
    result = CliRunner().invoke(
        app, ["--project", str(e2e_project.project), "init", e2e_project.name]
    )
    assert result.exit_code == 0
    mj = MicroJail.load(e2e_project.project)
    data_dir = e2e_project.project / mj.purge_path
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "secret.txt").write_text("hello")

    # Launch workshop
    e2e_project.launch()

    # Act
    result = CliRunner().invoke(app, ["--project", str(e2e_project.project), "destroy"])

    # Assert
    assert result.exit_code == 0, result.stderr
    assert not data_dir.exists()
    assert (e2e_project.project / ".microjail/config.yaml").exists()
