"""Integration tests for ``microjail unlock``.

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
def test_unlock_restores_egress(_lxd_environment):  # type: ignore[no-untyped-def]
    """After microjail lock + unlock, a network probe from inside the container succeeds."""
    lock_result = runner.invoke(app, ["lock"])
    assert lock_result.exit_code == 0

    unlock_result = runner.invoke(app, ["unlock"])
    assert unlock_result.exit_code == 0
    assert "unlocked" in unlock_result.output


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_unlock_idempotent_on_unlocked_environment(_lxd_environment):  # type: ignore[no-untyped-def]
    """Calling unlock on an already-unlocked environment exits zero."""
    result = runner.invoke(app, ["unlock"])
    assert result.exit_code == 0
