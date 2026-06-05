"""Unit tests for ``microjail unlock``.

Tests idempotency, successful unlock, and missing state file error.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from microjail.cli import app
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
        created_at=datetime(2026, 6, 2, 10, 0, 0, tzinfo=UTC),
        locked=locked,
    )
    state.to_json(tmp_path)


def test_unlock_exits_zero_when_already_unlocked(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``microjail unlock`` exits zero with informational message when already unlocked."""
    monkeypatch.chdir(tmp_path)
    _write_state(tmp_path, locked=False)
    result = runner.invoke(app, ["unlock"])
    assert result.exit_code == 0
    assert "already unlocked" in result.output


def test_unlock_exits_nonzero_when_no_state_file(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """``microjail unlock`` exits non-zero with helpful message when no state file exists."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["unlock"])
    assert result.exit_code != 0
    assert "microjail init" in result.output


@patch("microjail.commands.unlock.unlock_egress")
def test_unlock_restores_egress_and_updates_state(
    mock_unlock: MagicMock,
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """Successful unlock calls unlock_egress and sets locked=False in state."""
    monkeypatch.chdir(tmp_path)
    _write_state(tmp_path, locked=True)
    mock_unlock.return_value = None

    result = runner.invoke(app, ["unlock"])
    assert result.exit_code == 0
    assert "unlocked" in result.output
    mock_unlock.assert_called_once()

    loaded = State.from_json(tmp_path)
    assert loaded.locked is False


@patch("microjail.commands.unlock.unlock_egress")
def test_unlock_exits_nonzero_when_unlock_egress_fails(
    mock_unlock: MagicMock,
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """``microjail unlock`` exits non-zero when the LXD call fails."""
    monkeypatch.chdir(tmp_path)
    _write_state(tmp_path, locked=True)
    mock_unlock.side_effect = RuntimeError("lxc error: connection refused")

    result = runner.invoke(app, ["unlock"])
    assert result.exit_code != 0
    assert "lxc error" in result.output
