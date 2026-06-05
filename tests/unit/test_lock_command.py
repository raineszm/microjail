"""Unit tests for ``microjail lock``.

Covers idempotency, successful lock, gate failure with egress rollback,
and missing state file error.
"""

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from microjail.cli import app
from microjail.gates import GateResult
from microjail.state import State

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _write_state(tmp_path: Path, *, locked: bool) -> None:
    state = State(
        name="test-env",
        base_image="ubuntu@26.04",
        inference=None,
        agent=None,
        socket_url=None,
        locked=locked,
    )
    state.to_json(tmp_path)


def test_lock_exits_zero_when_already_locked(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``microjail lock`` exits zero with informational message when already locked."""
    monkeypatch.chdir(tmp_path)
    _write_state(tmp_path, locked=True)
    result = runner.invoke(app, ["lock"])
    assert result.exit_code == 0
    assert "already locked" in result.output


def test_lock_exits_nonzero_when_no_state_file(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``microjail lock`` exits non-zero with helpful message when no state file exists."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["lock"])
    assert result.exit_code != 0
    assert "microjail init" in result.output


@patch("microjail.commands.lock.run_all_gates")
@patch("microjail.commands.lock.lock_egress")
def test_lock_success_updates_state(
    mock_lock_egress: MagicMock,
    mock_run_gates: MagicMock,
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """Successful lock calls lock_egress, runs gates, and sets locked=True in state."""
    monkeypatch.chdir(tmp_path)
    _write_state(tmp_path, locked=False)
    mock_lock_egress.return_value = None
    mock_run_gates.return_value = [
        GateResult(name="egress", passed=True, message="Egress down"),
    ]

    result = runner.invoke(app, ["lock"])
    assert result.exit_code == 0
    assert "locked" in result.output
    mock_lock_egress.assert_called_once()

    loaded = State.from_json(tmp_path)
    assert loaded.locked is True


@patch("microjail.commands.lock.unlock_egress")
@patch("microjail.commands.lock.run_all_gates")
@patch("microjail.commands.lock.lock_egress")
def test_lock_gate_failure_triggers_egress_rollback(
    mock_lock_egress: MagicMock,
    mock_run_gates: MagicMock,
    mock_unlock_egress: MagicMock,
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """When a gate fails, egress is restored (rollback) before exiting non-zero."""
    monkeypatch.chdir(tmp_path)
    _write_state(tmp_path, locked=False)
    mock_lock_egress.return_value = None
    mock_run_gates.return_value = [
        GateResult(name="egress", passed=False, message="Egress still up"),
    ]
    mock_unlock_egress.return_value = None

    result = runner.invoke(app, ["lock"])
    assert result.exit_code != 0
    assert "egress" in result.output.lower()
    # Rollback must be called.
    mock_unlock_egress.assert_called_once()

    # State must NOT be updated to locked=True after failure.
    loaded = State.from_json(tmp_path)
    assert loaded.locked is False


@patch("microjail.commands.lock.unlock_egress")
@patch("microjail.commands.lock.run_all_gates")
@patch("microjail.commands.lock.lock_egress")
def test_lock_gate_failure_rollback_survives_unlock_error(
    mock_lock_egress: MagicMock,
    mock_run_gates: MagicMock,
    mock_unlock_egress: MagicMock,
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """Gate failure exits non-zero even when the rollback unlock also fails."""
    monkeypatch.chdir(tmp_path)
    _write_state(tmp_path, locked=False)
    mock_lock_egress.return_value = None
    mock_run_gates.return_value = [
        GateResult(name="workspace", passed=False, message="Workspace not mounted"),
    ]
    mock_unlock_egress.side_effect = RuntimeError("cannot restore egress")

    result = runner.invoke(app, ["lock"])
    assert result.exit_code != 0
    assert "workspace" in result.output.lower()
