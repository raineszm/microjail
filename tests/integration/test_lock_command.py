"""Integration tests for ``microjail lock``.

Requires a live Workshop + LXD installation.
Run with: uv run pytest -m lxd tests/integration/test_lock_command.py
"""

import pytest
from typer.testing import CliRunner

from microjail.cli import app

runner = CliRunner()


@pytest.mark.lxd
def test_lock_severs_egress(lxd_environment):  # type: ignore[no-untyped-def]
    """After microjail lock, a network probe from inside the container fails."""
    result = runner.invoke(app, ["lock"])
    assert result.exit_code == 0
    assert "locked" in result.output

    # Clean up.
    runner.invoke(app, ["unlock"])


@pytest.mark.lxd
def test_lock_idempotent_on_locked_environment(lxd_environment):  # type: ignore[no-untyped-def]
    """Calling lock on an already-locked environment exits zero."""
    runner.invoke(app, ["lock"])
    result = runner.invoke(app, ["lock"])
    assert result.exit_code == 0
    assert "already locked" in result.output

    runner.invoke(app, ["unlock"])


@pytest.mark.lxd
def test_lock_state_records_locked(lxd_environment, tmp_path):  # type: ignore[no-untyped-def]
    """After microjail lock, state.json records locked=True."""
    from pathlib import Path

    from microjail.state import State

    result = runner.invoke(app, ["lock"])
    assert result.exit_code == 0
    state = State.from_json(Path.cwd())
    assert state.locked is True

    runner.invoke(app, ["unlock"])
