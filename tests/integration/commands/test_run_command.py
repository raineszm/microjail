"""Integration tests for ``microjail run``.

These tests require a live Workshop + LXD installation.  They are skipped
automatically when the required services are unavailable.  Long-running tests
(those that create containers) additionally require ``--run-long``::

    uv run pytest --run-long tests/integration/commands/test_run_command.py
"""

import socket

import pytest
from typer.testing import CliRunner

from microjail.cli import app

runner = CliRunner()


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_run_echo_hello_exits_zero(lxd_environment):  # type: ignore[no-untyped-def]
    """``microjail run -- echo hello`` executes and exits with the workload's exit code."""
    result = runner.invoke(app, ["run", "echo", "hello"])
    assert result.exit_code == 0


def test_run_fails_when_no_state_file(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """``microjail run`` exits non-zero when no state file exists."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "echo", "hello"])
    assert result.exit_code != 0
    assert "microjail init" in result.output


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_run_fails_when_workload_empty(lxd_environment):  # type: ignore[no-untyped-def]
    """``microjail run`` with no workload tokens exits non-zero before locking."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code != 0
    assert "No workload command" in result.output


# ---------------------------------------------------------------------------
# T029: Inference tunnel gate — TCP endpoint unreachable
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_run_fails_when_inference_tunnel_unreachable(lxd_inference_environment):  # type: ignore[no-untyped-def]
    """When --inference llama-cpp was set at init and the TCP endpoint is unreachable,
    ``microjail run`` exits non-zero and names the unreachable host:port.
    """
    # lxd_inference_environment fixture provides an environment initialised with
    # --inference llama-cpp; no inference server is running on the host.
    result = runner.invoke(app, ["run", "echo", "hello"])
    assert result.exit_code != 0
    # The error message should reference the expected endpoint or the gate name.
    assert any(
        keyword in result.output.lower()
        for keyword in ("tunnel", "inference", "localhost:8080", "not reachable")
    )


# ---------------------------------------------------------------------------
# T030: Inference tunnel gate — TCP endpoint reachable
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_run_succeeds_when_inference_tunnel_reachable(  # type: ignore[no-untyped-def]
    lxd_inference_environment,
) -> None:
    """When --inference llama-cpp was set at init and a TCP server is listening
    on localhost:8080, the inference tunnel gate passes and the run proceeds.
    """
    # Bind a TCP socket on port 8080 so the gate can connect.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 8080))
    srv.listen(1)
    try:
        result = runner.invoke(app, ["run", "echo", "hello"])
        assert result.exit_code == 0
    finally:
        srv.close()
