"""Integration tests for ``microjail run``.

These tests require a live Workshop + LXD installation.  They are skipped
automatically when the required services are unavailable.  Long-running tests
(those that create containers) additionally require ``--run-long``::

    uv run pytest --run-long tests/integration/commands/test_run_command.py
"""

import socket
import subprocess
import uuid

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


# ---------------------------------------------------------------------------
# T020: Lazy launch via microjail run (SC-004)
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_run_lazy_launches_unlaunched_environment_and_unlocks_after_success(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch
) -> None:
    """First ``microjail run`` on a configured-not-launched env provisions the container.

    After ``init`` (no lock), the container does not exist.  ``run`` triggers
    lazy launch, executes the workload, unlocks, and leaves state with
    ``launched=True, locked=False``.
    """
    from microjail.state import State

    monkeypatch.chdir(tmp_path)
    name = f"mj-run-lazy-{uuid.uuid4().hex[:8]}"
    try:
        result = runner.invoke(app, ["init", name], catch_exceptions=False)
        assert result.exit_code == 0, f"init failed:\n{result.output}"

        # Container must NOT exist yet.
        info = subprocess.run(
            ["workshop", "info", name, "--project", str(tmp_path)],
            capture_output=True,
            check=False,
        )
        assert info.returncode != 0, "Container found before run — expected absent"

        result = runner.invoke(
            app, ["run", "--", "echo", "hello"], catch_exceptions=False
        )
        assert result.exit_code == 0, f"run failed:\n{result.output}"

        # Container must now exist.
        info = subprocess.run(
            ["workshop", "info", name, "--project", str(tmp_path)],
            capture_output=True,
            check=False,
        )
        assert info.returncode == 0, "Container not found after run"

        # State must reflect launched=True, locked=False.
        state = State.from_json(tmp_path)
        assert state.launched is True
        assert state.locked is False
    finally:
        subprocess.run(
            ["workshop", "remove", name, "--project", str(tmp_path)],
            capture_output=True,
            check=False,
        )
