"""Unit tests for ``microjail init`` pre-flight checks.

Covers workspace writability, duplicate detection via local state file, and
--force path behaviour.  No Workshop subprocess is called on the normal init
path or on --force for an unlaunched environment.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from microjail.cli import app
from microjail.state import STATE_DIR, STATE_FILE, State

runner = CliRunner()


# ---------------------------------------------------------------------------
# Workspace writability (FR-006)
# ---------------------------------------------------------------------------


def test_non_writable_workspace_exits_nonzero() -> None:
    """Init exits non-zero when the workspace directory is not writable."""
    with patch("microjail.commands.init.os.access", return_value=False):
        result = runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    assert result.exit_code != 0


def test_non_writable_workspace_message_contains_path() -> None:
    """Error message names the failing workspace path."""
    workspace = Path.cwd()
    with patch("microjail.commands.init.os.access", return_value=False):
        result = runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    assert str(workspace) in result.output or str(workspace) in (result.stderr or "")


def test_non_writable_workspace_no_workshop_call() -> None:
    """No Workshop subprocess is called when the workspace is not writable."""
    with (
        patch("microjail.commands.init.os.access", return_value=False),
        patch("microjail.commands.init.workshop.launch") as mock_launch,
        patch("microjail.commands.init.workshop.check_prerequisites") as mock_prereq,
    ):
        runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    mock_launch.assert_not_called()
    mock_prereq.assert_not_called()


# ---------------------------------------------------------------------------
# Normal init makes zero Workshop subprocess calls (FR-001, SC-002)
# ---------------------------------------------------------------------------


def test_normal_init_makes_no_workshop_calls(tmp_path: Path) -> None:
    """Normal init calls no Workshop subprocess at all."""
    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
        patch("microjail.commands.init.workshop.launch") as mock_launch,
        patch("microjail.commands.init.workshop.refresh") as mock_refresh,
        patch("microjail.commands.init.workshop.verify_exists") as mock_verify,
        patch("microjail.commands.init.workshop.connect") as mock_connect,
        patch("microjail.commands.init.workshop.check_prerequisites") as mock_prereq,
    ):
        result = runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    mock_launch.assert_not_called()
    mock_refresh.assert_not_called()
    mock_verify.assert_not_called()
    mock_connect.assert_not_called()
    mock_prereq.assert_not_called()


def test_normal_init_writes_state_with_launched_false(tmp_path: Path) -> None:
    """Normal init writes state.json with launched=False (FR-003)."""
    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
    ):
        result = runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    state = State.from_json(tmp_path)
    assert state.launched is False
    assert state.locked is False


# ---------------------------------------------------------------------------
# Duplicate detection via local state file (FR-005)
# ---------------------------------------------------------------------------


def test_writable_workspace_duplicate_detected_via_state_file(
    tmp_path: Path,
) -> None:
    """Init exits 2 with 'already exists' when state.json is present, even without
    a running Workshop environment."""
    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
    ):
        # First init succeeds.
        runner.invoke(app, ["init", "testenv"], catch_exceptions=False)
        # Second init without --force must be rejected.
        result = runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    assert result.exit_code == 2
    assert "already exists" in result.output


# ---------------------------------------------------------------------------
# --force on unlaunched environment (FR-011)
# ---------------------------------------------------------------------------


def test_force_on_unlaunched_env_writes_files_without_workshop_calls(
    tmp_path: Path,
) -> None:
    """--force on launched=False rewrites config files with zero Workshop calls."""
    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
    ):
        runner.invoke(app, ["init", "testenv"], catch_exceptions=False)

    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
        patch("microjail.commands.init.workshop.launch") as mock_launch,
        patch("microjail.commands.init.workshop.refresh") as mock_refresh,
        patch("microjail.commands.init.workshop.check_prerequisites") as mock_prereq,
    ):
        result = runner.invoke(
            app, ["init", "testenv", "--force"], catch_exceptions=False
        )

    assert result.exit_code == 0, result.output
    mock_launch.assert_not_called()
    mock_refresh.assert_not_called()
    mock_prereq.assert_not_called()
    # State must still say launched=False.
    state = State.from_json(tmp_path)
    assert state.launched is False


# ---------------------------------------------------------------------------
# --force on launched environment (FR-012)
# ---------------------------------------------------------------------------


def test_force_launched_env_calls_refresh_not_launch(tmp_path: Path) -> None:
    """--force on launched=True calls refresh + verify_exists; launch not called."""
    # Write a state file that claims launched=True.
    State(
        name="testenv",
        base_image="ubuntu@26.04",
        inference=None,
        agent=None,
        socket_url=None,
        launched=True,
    ).dump(tmp_path)

    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
        patch(
            "microjail.commands.init.workshop.check_prerequisites", return_value=None
        ),
        patch(
            "microjail.commands.init.workshop.refresh", return_value=None
        ) as mock_refresh,
        patch(
            "microjail.commands.init.workshop.verify_exists", return_value=None
        ) as mock_verify,
        patch(
            "microjail.commands.init.workshop.launch", return_value=None
        ) as mock_launch,
    ):
        result = runner.invoke(
            app, ["init", "testenv", "--force"], catch_exceptions=False
        )

    assert result.exit_code == 0, result.output
    mock_refresh.assert_called_once()
    mock_verify.assert_called_once()
    mock_launch.assert_not_called()
    # launched must remain True after --force on launched env.
    state = State.from_json(tmp_path)
    assert state.launched is True


# ---------------------------------------------------------------------------
# --force on locked environment (FR-017)
# ---------------------------------------------------------------------------


def test_force_on_locked_env_exits_2(tmp_path: Path) -> None:
    """--force on locked=True exits 2 with an actionable message; no Workshop calls."""
    State(
        name="testenv",
        base_image="ubuntu@26.04",
        inference=None,
        agent=None,
        socket_url=None,
        launched=True,
        locked=True,
    ).dump(tmp_path)

    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
        patch("microjail.commands.init.workshop.refresh") as mock_refresh,
        patch("microjail.commands.init.workshop.check_prerequisites") as mock_prereq,
    ):
        result = runner.invoke(
            app, ["init", "testenv", "--force"], catch_exceptions=False
        )

    assert result.exit_code == 2
    assert "unlock" in result.output.lower()
    mock_refresh.assert_not_called()
    mock_prereq.assert_not_called()


# ---------------------------------------------------------------------------
# state.json is always written on successful normal init (even without Workshop)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("inference", [None, "llama-cpp"])
def test_state_written_with_launched_false_on_normal_init(
    tmp_path: Path, inference: str | None
) -> None:
    """state.json is written with launched=False on every successful normal init."""
    args = ["init", "testenv"]
    if inference:
        args += ["--inference", inference]

    with (
        patch("microjail.commands.init.os.access", return_value=True),
        patch("microjail.commands.init.Path.cwd", return_value=tmp_path),
    ):
        result = runner.invoke(app, args, catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert (tmp_path / STATE_DIR / STATE_FILE).exists()
    state = State.from_json(tmp_path)
    assert state.launched is False
