"""End-to-end tests for the CLI workflow against a real Workshop."""

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from microjail.adapters import workshop
from microjail.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    from tests._helpers import SharedWorkshop

NETWORK_PROBE_TIMEOUT = 10


# -- helpers --


def has_egress(ws: SharedWorkshop) -> bool:
    """Return True if the workshop container can reach the internet."""
    result = workshop.exec_(
        ws.name,
        ws.path,
        [
            "python3",
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5).close()",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=NETWORK_PROBE_TIMEOUT,
    )
    return result.returncode == 0


def can_write_config(ws: SharedWorkshop) -> bool:
    """Return True if /project/.microjail/config.yaml is writable inside the container."""
    result = workshop.exec_(
        ws.name,
        ws.path,
        ["test", "-w", "/project/.microjail/config.yaml"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


# -- lock --


def test_lock_blocks_egress(e2e_workshop: SharedWorkshop) -> None:
    """`microjail lock` prevents network egress from the container."""
    if not has_egress(e2e_workshop):
        pytest.skip("workshop lacks baseline network egress")

    result = CliRunner().invoke(app, ["lock"])
    assert result.exit_code == 0, result.stderr

    assert not has_egress(e2e_workshop)


def test_lock_makes_config_readonly(e2e_workshop: SharedWorkshop) -> None:
    """`microjail lock` makes the config file read-only inside the container."""
    if not can_write_config(e2e_workshop):
        pytest.skip("workshop config not writable at baseline")

    result = CliRunner().invoke(app, ["lock"])
    assert result.exit_code == 0, result.stderr

    assert not can_write_config(e2e_workshop)


# -- run --


def test_run_propagates_exit_code(e2e_workshop: SharedWorkshop) -> None:
    """`microjail run -- <cmd>` returns the workload's exit code."""
    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "exit 7"])

    assert result.exit_code == 7


def test_run_enforces_lockdown_before_workload(e2e_workshop: SharedWorkshop) -> None:
    """`microjail run` applies lockdown before starting the workload.

    A network probe run inside the jail should fail because the gate blocks egress.
    """
    if not has_egress(e2e_workshop):
        pytest.skip("workshop lacks baseline network egress")

    result = CliRunner().invoke(
        app,
        [
            "run",
            "--",
            "python3",
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5).close()",
        ],
    )

    assert result.exit_code != 0


def test_run_workload_succeeds(e2e_workshop: SharedWorkshop) -> None:
    """`microjail run` executes the workload and returns its exit code (0 on success).

    ``CliRunner`` cannot capture ``subprocess.run`` stdout, so we only check
    the exit code.
    """
    result = CliRunner().invoke(app, ["run", "--", "sh", "-c", "true"])

    assert result.exit_code == 0


# -- missing config --


def test_lock_fails_without_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`microjail lock` fails with a helpful message when no config exists."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 1
    assert "No microjail config found" in result.stderr


def test_run_fails_without_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`microjail run` fails with a helpful message when no config exists."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["run", "--", "true"])

    assert result.exit_code == 1
    assert "No microjail config found" in result.stderr


def test_unlock_fails_without_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`microjail unlock` fails with a helpful message when no config exists."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["unlock"])

    assert result.exit_code == 1
    assert "No microjail config found" in result.stderr
