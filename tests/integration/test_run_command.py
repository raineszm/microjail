"""Integration tests for ``microjail run``.

These tests require a live Workshop + LXD installation and are marked
``@pytest.mark.lxd`` so they are excluded from the default test run
(``addopts = "-m 'not lxd'"`` in pyproject.toml).

Run with: uv run pytest -m lxd tests/integration/test_run_command.py
"""

import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from microjail.cli import app

runner = CliRunner()


@pytest.mark.lxd
def test_run_echo_hello_exits_zero(lxd_environment):  # type: ignore[no-untyped-def]
    """``microjail run -- echo hello`` executes and exits with the workload's exit code."""
    result = runner.invoke(app, ["run", "echo", "hello"])
    assert result.exit_code == 0


@pytest.mark.lxd
def test_run_fails_when_no_state_file(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """``microjail run`` exits non-zero when no state file exists."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "echo", "hello"])
    assert result.exit_code != 0
    assert "microjail init" in result.output


@pytest.mark.lxd
def test_run_fails_when_workload_empty(lxd_environment):  # type: ignore[no-untyped-def]
    """``microjail run`` with no workload tokens exits non-zero before locking."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code != 0
    assert "No workload command" in result.output


# ---------------------------------------------------------------------------
# T029: Inference socket gate — socket absent
# ---------------------------------------------------------------------------


@pytest.mark.lxd
def test_run_fails_when_inference_socket_missing(lxd_inference_environment):  # type: ignore[no-untyped-def]
    """When --inference llama-cpp was set at init and the socket file is absent,
    ``microjail run`` exits non-zero and names the missing socket path.
    """
    # lxd_inference_environment fixture provides an environment initialised with
    # --inference llama-cpp; no socket file is placed on the host.
    result = runner.invoke(app, ["run", "echo", "hello"])
    assert result.exit_code != 0
    # The error message should reference the expected socket path or the gate name.
    assert any(
        keyword in result.output.lower()
        for keyword in ("socket", "inference", "inference_socket")
    )


# ---------------------------------------------------------------------------
# T030: Inference socket gate — socket present
# ---------------------------------------------------------------------------


@pytest.mark.lxd
def test_run_succeeds_when_inference_socket_present(  # type: ignore[no-untyped-def]
    lxd_inference_environment, tmp_path
) -> None:
    """When --inference llama-cpp was set at init and a UDS socket is listening
    at the expected path, the inference socket gate passes and the run proceeds.
    """
    from microjail.state import EnvironmentState

    state = EnvironmentState.from_json(Path.cwd())
    assert state.socket_url is not None

    # Extract socket path from the socket_url (unix:///path/to/socket.sock).
    socket_path_str = state.socket_url.removeprefix("unix://")
    socket_path = Path(socket_path_str)
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    # Bind a UDS socket at the expected path so the gate can connect.
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(socket_path))
    srv.listen(1)
    try:
        result = runner.invoke(app, ["run", "echo", "hello"])
        assert result.exit_code == 0
    finally:
        srv.close()
        socket_path.unlink(missing_ok=True)
