"""Unit tests for CTF CLI argument parsing."""

from unittest.mock import patch

from typer.testing import CliRunner

from ctf.cli import app
from ctf.report import CtfReport

runner = CliRunner()


def _patch_runner():
    """Patch run_ctf so we never actually execute the CTF pipeline."""
    fake_verdict = CtfReport(
        outcome="PASS",
        error_kind=None,
        elapsed=0.0,
        timeout=300.0,
        secret_match=False,
        breach_vector=None,
        run_id="test-run",
    )
    return patch("ctf.cli.run_ctf", return_value=fake_verdict)


class TestHelpOutput:
    def test_help_shows_model_option(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--model" in result.output

    def test_help_shows_endpoint_option(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--endpoint" in result.output

    def test_help_shows_keep_on_failure_option(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--keep-on-failure" in result.output

    def test_help_shows_timeout_option(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--timeout" in result.output


class TestDefaultValues:
    def test_default_endpoint_in_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "localhost:8080" in result.output

    def test_default_timeout_in_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "300" in result.output


class TestRequiredModel:
    def test_missing_model_exits_with_error(self):
        result = runner.invoke(app, [])
        assert result.exit_code != 0

    def test_missing_model_shows_error_message(self):
        result = runner.invoke(app, [])
        assert result.exit_code != 0
        assert "model" in result.output.lower() or "missing" in result.output.lower()


class TestModelOption:
    def test_model_flag_accepted(self):
        with _patch_runner():
            result = runner.invoke(app, ["--model", "test-model"])
            assert result.exit_code == 0

    def test_model_passed_to_runner(self):
        with _patch_runner() as mock_run:
            runner.invoke(app, ["--model", "test-model"])
            call_args = mock_run.call_args
            config = call_args[0][0]
            assert config.model == "test-model"


class TestEndpointOption:
    def test_custom_endpoint_accepted(self):
        with _patch_runner() as mock_run:
            result = runner.invoke(
                app, ["--model", "m", "--endpoint", "localhost:11434"]
            )
            assert result.exit_code == 0
            config = mock_run.call_args[0][0]
            assert config.endpoint == "localhost:11434"

    def test_default_endpoint_used_when_not_specified(self):
        with _patch_runner() as mock_run:
            result = runner.invoke(app, ["--model", "m"])
            assert result.exit_code == 0
            config = mock_run.call_args[0][0]
            assert config.endpoint == "localhost:8080"


class TestKeepOnFailureOption:
    def test_keep_on_failure_flag_accepted(self):
        with _patch_runner() as mock_run:
            result = runner.invoke(app, ["--model", "m", "--keep-on-failure"])
            assert result.exit_code == 0
            config = mock_run.call_args[0][0]
            assert config.keep_on_failure is True

    def test_keep_on_failure_defaults_to_false(self):
        with _patch_runner() as mock_run:
            result = runner.invoke(app, ["--model", "m"])
            assert result.exit_code == 0
            config = mock_run.call_args[0][0]
            assert config.keep_on_failure is False


class TestTimeoutOption:
    def test_custom_timeout_accepted(self):
        with _patch_runner() as mock_run:
            result = runner.invoke(app, ["--model", "m", "--timeout", "60"])
            assert result.exit_code == 0
            config = mock_run.call_args[0][0]
            assert config.timeout == 60.0

    def test_default_timeout_used_when_not_specified(self):
        with _patch_runner() as mock_run:
            result = runner.invoke(app, ["--model", "m"])
            assert result.exit_code == 0
            config = mock_run.call_args[0][0]
            assert config.timeout == 300.0
