"""Implementation of ``microjail run``.

Execution order (FR-015 through FR-019):
1. Validate the workload command is non-empty.
2. Load state from ``.microjail/state.json``.
3. Delegate to ``perform_lock()`` (same logic as ``microjail lock``).
4. Spawn the workload inside the container via ``workshop.client.exec_in_env()``.
5. Write the run log entry to ``.microjail/run-log.jsonl`` (FR-021).
6. Unlock (restore egress, update state).
7. Exit with the workload's exit code.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from microjail.commands.lock import perform_lock
from microjail.lxd.network import unlock_egress
from microjail.state import STATE_DIR, STATE_FILE, EnvironmentState
from microjail.workshop import client as workshop

_RUN_LOG_FILE = ".microjail/run-log.jsonl"


def _write_run_log(
    workspace: Path,
    state: EnvironmentState,
    workload: list[str],
    start_time: datetime,
    gate_results: list[dict[str, object]],
    exit_code: int,
) -> None:
    """Append a JSONL run log entry to ``.microjail/run-log.jsonl``.

    The log MUST be written even when the workload exits non-zero (FR-021).
    Raises :exc:`OSError` if the file cannot be written — the caller surfaces
    this as a warning rather than masking it (constitution §V).
    """
    log_path = workspace / _RUN_LOG_FILE
    entry = {
        "environment": state.name,
        "workload": workload,
        "started_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gates": gate_results,
        "exit_code": exit_code,
    }
    with log_path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def run(
    workload: Annotated[
        list[str] | None,
        typer.Argument(help="Command to run inside the container."),
    ] = None,
) -> None:
    r"""Lock the environment, run WORKLOAD inside the container, then unlock.

    \b
    Reads .microjail/state.json from the current directory. Locks the
    environment (cuts egress + verifies all gates) before spawning the
    workload. Unlocks after the workload exits. Exits with the workload's
    exit code.

    \b
    Examples:
      microjail run -- opencode run "refactor the parser module"
      microjail run -- bash -c "echo hello"
    """
    if not workload:
        typer.echo(
            "Error: No workload command provided. Usage: microjail run -- <command>",
            err=True,
        )
        raise typer.Exit(1)

    workspace = Path.cwd()
    state_path = workspace / STATE_DIR / STATE_FILE

    if not state_path.exists():
        typer.echo(
            "Error: No microjail environment found in the current directory. "
            "Run 'microjail init' first.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        state = EnvironmentState.from_json(workspace)
    except ValueError as exc:
        typer.echo(f"Error: Cannot read state file: {exc}", err=True)
        raise typer.Exit(1) from exc

    start_time = datetime.now(tz=UTC)

    # Lock (cuts egress + runs all gates).
    try:
        perform_lock(state, workspace)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    # Spawn workload.
    try:
        proc = workshop.exec_in_env(state.name, list(workload), workspace)
    except RuntimeError as exc:
        typer.echo(f"Error: Cannot execute workload: {exc}", err=True)
        _unlock_after_run(state, workspace)
        raise typer.Exit(1) from exc

    exit_code = proc.returncode

    # Write run log (FR-021) — before unlocking so exit_code is captured.
    gate_results: list[dict[str, object]] = []  # gates already ran inside perform_lock
    try:
        _write_run_log(
            workspace, state, list(workload), start_time, gate_results, exit_code
        )
    except OSError as exc:
        # Log failure is a warning, not fatal (constitution §V: surface it).
        typer.echo(f"Warning: Could not write run log: {exc}", err=True)

    # Unlock (restore egress, update state).
    _unlock_after_run(state, workspace)

    raise typer.Exit(exit_code)


def _unlock_after_run(state: EnvironmentState, workspace: Path) -> None:
    """Restore egress and mark state as unlocked after a run completes."""
    try:
        unlock_egress(state.name)
    except RuntimeError as exc:
        typer.echo(
            f"Warning: Could not restore egress after run: {exc}\n"
            "Run 'microjail unlock' to restore networking manually.",
            err=True,
        )
        return
    state.locked = False
    try:
        state.to_json(workspace)
    except OSError as exc:
        typer.echo(
            f"Warning: Could not update state file after unlock: {exc}", err=True
        )
