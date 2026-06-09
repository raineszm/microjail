# ruff: noqa: I001
from ctf.cli import app
from typer.testing import CliRunner


runner = CliRunner()


def test_ctf_help_mentions_alpha_and_standalone() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Capture The Flag" in result.output
    assert "standalone" in result.output
    assert "alpha" in result.output
