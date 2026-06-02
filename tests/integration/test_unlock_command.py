"""Integration tests for ``microjail unlock``.

Requires a live Workshop + LXD installation.
Run with: uv run pytest -m lxd tests/integration/test_unlock_command.py
"""

import pytest
from typer.testing import CliRunner

from microjail.cli import app

runner = CliRunner()


@pytest.mark.lxd
def test_unlock_restores_egress(lxd_environment):  # type: ignore[no-untyped-def]
    """After microjail lock + unlock, a network probe from inside the container succeeds."""
    lock_result = runner.invoke(app, ["lock"])
    assert lock_result.exit_code == 0

    unlock_result = runner.invoke(app, ["unlock"])
    assert unlock_result.exit_code == 0
    assert "unlocked" in unlock_result.output


@pytest.mark.lxd
def test_unlock_idempotent_on_unlocked_environment(lxd_environment):  # type: ignore[no-untyped-def]
    """Calling unlock on an already-unlocked environment exits zero."""
    result = runner.invoke(app, ["unlock"])
    assert result.exit_code == 0
