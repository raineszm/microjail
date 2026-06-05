"""Integration tests for ``microjail lock``.

Requires a live Workshop + LXD installation.  Tests are skipped automatically
when the required services are unavailable; pass ``--run-long`` to include.
"""

import pytest
from typer.testing import CliRunner

from microjail.cli import app

runner = CliRunner()


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_lock_severs_egress(_lxd_environment):  # type: ignore[no-untyped-def]
    """After microjail lock, a network probe from inside the container fails."""
    result = runner.invoke(app, ["lock"])
    assert result.exit_code == 0
    assert "locked" in result.output

    # Clean up.
    runner.invoke(app, ["unlock"])


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_lock_idempotent_on_locked_environment(_lxd_environment):  # type: ignore[no-untyped-def]
    """Calling lock on an already-locked environment exits zero."""
    runner.invoke(app, ["lock"])
    result = runner.invoke(app, ["lock"])
    assert result.exit_code == 0
    assert "already locked" in result.output

    runner.invoke(app, ["unlock"])


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_lock_state_records_locked(_lxd_environment):  # type: ignore[no-untyped-def]
    """After microjail lock, state.json records locked=True."""
    from pathlib import Path

    from microjail.state import State

    result = runner.invoke(app, ["lock"])
    assert result.exit_code == 0
    state = State.from_json(Path.cwd())
    assert state.locked is True

    runner.invoke(app, ["unlock"])
