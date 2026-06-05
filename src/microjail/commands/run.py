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

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from microjail.commands import load_state_or_exit
from microjail.commands.lock import perform_lock
from microjail.output import err, warn
from microjail.wrappers import workshop
from microjail.wrappers.lxd import unlock_egress

if TYPE_CHECKING:
    from microjail.state import State


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
        err("No workload command provided. Usage: microjail run -- <command>")

    workspace = Path.cwd()
    state = load_state_or_exit(workspace)
    try:
        perform_lock(state, workspace)
    except RuntimeError as exc:
        err(str(exc))

    # Spawn workload.
    try:
        proc = workshop.exec_in_env(state.name, list(workload), workspace)
    except RuntimeError as exc:
        typer.echo(f"Error: Cannot execute workload: {exc}", err=True)
        unlock_after_run(state, workspace)
        raise typer.Exit(1) from exc

    exit_code = proc.returncode

    # Unlock (restore egress, update state).
    unlock_after_run(state, workspace)

    raise typer.Exit(exit_code)


def unlock_after_run(state: State, workspace: Path) -> None:
    """Restore egress and mark state as unlocked after a run completes."""
    try:
        unlock_egress(state.name)
        state.locked = False
        state.dump(workspace)
    except RuntimeError as exc:
        warn(
            f"Could not restore egress after run: {exc}\n"
            "Run 'microjail unlock' to restore networking manually."
        )
    except OSError as exc:
        warn(f"Could not update state file after unlock: {exc}")
