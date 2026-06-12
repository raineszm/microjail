from typing import TYPE_CHECKING

from typer.testing import CliRunner

from microjail.cli import app
from microjail.microjail import MicroJail
from tests.marks import requires_lxd, requires_workshop

pytestmark = [
    requires_lxd(),
    requires_workshop(),
]
if TYPE_CHECKING:
    from pathlib import Path


def test_init_creates_purge_path(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["--project", str(tmp_path), "init", "test-jail"])
    assert result.exit_code == 0, result.stderr

    loaded = MicroJail.load(tmp_path)
    assert getattr(loaded, "purge_path", None) == "data"
    assert (tmp_path / "data").is_dir()
