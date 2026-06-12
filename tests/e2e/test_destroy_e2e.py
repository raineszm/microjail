from typing import TYPE_CHECKING

from typer.testing import CliRunner

from microjail.adapters import workshop
from microjail.cli import app
from microjail.microjail import MicroJail

if TYPE_CHECKING:
    from tests._helpers import SharedWorkshop


def test_destroy_default_behavior(e2e_project: SharedWorkshop) -> None:
    # Arrange
    result = CliRunner().invoke(
        app, ["--project", str(e2e_project.path), "init", e2e_project.name]
    )
    assert result.exit_code == 0
    mj = MicroJail.load(e2e_project.path)
    data_dir = e2e_project.path / mj.purge_path
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "secret.txt").write_text("hello")

    # Launch workshop
    workshop.launch(e2e_project.name, project=e2e_project.path)

    # Act
    result = CliRunner().invoke(app, ["--project", str(e2e_project.path), "destroy"])

    # Assert
    assert result.exit_code == 0, result.stderr
    assert not data_dir.exists()
    assert (e2e_project.path / ".microjail/config.yaml").exists()
