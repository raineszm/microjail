"""Unit tests for workspace writability pre-flight check (T006b/T006c).

Tests that ``microjail init`` refuses to proceed when the workspace directory
is not writable, without making any Workshop subprocess calls.
"""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from microjail.cli import app

runner = CliRunner()


def test_non_writable_workspace_exits_nonzero(tmp_path: Path) -> None:
    """Init exits non-zero when the workspace directory is not writable."""
    with (
        patch("microjail.commands.init.os.access", return_value=False),
        patch(
            "microjail.commands.init.client.check_prerequisites",
            return_value=None,
        ),
        patch(
            "microjail.commands.init.client.environment_exists",
            return_value=False,
        ),
    ):
        result = runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    assert result.exit_code != 0


def test_non_writable_workspace_message_contains_path(tmp_path: Path) -> None:
    """Error message names the failing workspace path."""
    workspace = Path.cwd()
    with (
        patch("microjail.commands.init.os.access", return_value=False),
        patch(
            "microjail.commands.init.client.check_prerequisites",
            return_value=None,
        ),
        patch(
            "microjail.commands.init.client.environment_exists",
            return_value=False,
        ),
    ):
        result = runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    # The error message must contain the workspace path so the user knows which
    # directory failed (Principle V: fail loudly, fail clearly).
    assert str(workspace) in result.output or str(workspace) in (result.stderr or "")


def test_non_writable_workspace_no_workshop_call(tmp_path: Path) -> None:
    """Workshop subprocess is never called when the workspace is not writable."""
    with (
        patch("microjail.commands.init.os.access", return_value=False),
        patch(
            "microjail.commands.init.client.check_prerequisites",
            return_value=None,
        ) as mock_prereq,
        patch(
            "microjail.commands.init.client.environment_exists",
            return_value=False,
        ),
        patch(
            "microjail.commands.init.client.launch",
        ) as mock_launch,
    ):
        runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    mock_launch.assert_not_called()
    # prerequisites check runs before the writability probe — that is expected
    mock_prereq.assert_called_once()


def test_writable_workspace_proceeds(tmp_path: Path) -> None:
    """Init proceeds past the writability check when workspace is writable."""
    # When os.access returns True, execution should move past the probe.
    # We stop it at the environment-exists check to avoid full orchestration.
    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch(
            "microjail.commands.init.client.check_prerequisites",
            return_value=None,
        ),
        patch(
            "microjail.commands.init.client.environment_exists",
            return_value=True,  # triggers "already exists" exit so we stop early
        ),
    ):
        result = runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    # Should fail with "already exists", not a writability error
    assert "writable" not in result.output
    assert "already exists" in result.output


def test_force_bypasses_environment_exists_check(tmp_path: Path) -> None:
    """--force allows reinitialisation when the environment already exists."""
    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch(
            "microjail.commands.init.client.check_prerequisites",
            return_value=None,
        ),
        patch(
            "microjail.commands.init.client.environment_exists",
            return_value=True,  # environment already exists
        ),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
        patch(
            "microjail.commands.init.client.refresh",
            return_value=None,
        ),
        patch(
            "microjail.commands.init.client.verify_exists",
            return_value=None,
        ),
    ):
        result = runner.invoke(
            app, ["init", "testenv", "--force"], catch_exceptions=False
        )

    # --force must not be blocked by the "already exists" guard
    assert "already exists" not in result.output
    assert result.exit_code == 0


def test_force_calls_refresh_not_launch_when_env_exists(tmp_path: Path) -> None:
    """When environment already exists, --force triggers refresh, not launch."""
    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.client.check_prerequisites", return_value=None),
        patch("microjail.commands.init.client.environment_exists", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
        patch(
            "microjail.commands.init.client.refresh", return_value=None
        ) as mock_refresh,
        patch(
            "microjail.commands.init.client.launch", return_value=None
        ) as mock_launch,
        patch("microjail.commands.init.client.verify_exists", return_value=None),
    ):
        runner.invoke(app, ["init", "testenv", "--force"], catch_exceptions=False)

    mock_refresh.assert_called_once()
    mock_launch.assert_not_called()


def test_new_env_calls_launch_not_refresh(tmp_path: Path) -> None:
    """When no environment exists, init calls launch, not refresh."""
    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.client.check_prerequisites", return_value=None),
        patch("microjail.commands.init.client.environment_exists", return_value=False),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
        patch(
            "microjail.commands.init.client.refresh", return_value=None
        ) as mock_refresh,
        patch(
            "microjail.commands.init.client.launch", return_value=None
        ) as mock_launch,
        patch("microjail.commands.init.client.verify_exists", return_value=None),
    ):
        runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    mock_launch.assert_called_once()
    mock_refresh.assert_not_called()
