"""Implementation of ``microjail unlock``.

Restores network egress to the container and marks the environment as unlocked
in the state file.  Idempotent: calling on an already-unlocked environment
exits zero with an informational message (FR-014).
"""

from pathlib import Path

import typer

from microjail.lxd.network import unlock_egress
from microjail.state import STATE_DIR, STATE_FILE, EnvironmentState


def unlock() -> None:
    r"""Restore network egress after a locked run.

    \b
    Reads .microjail/state.json from the current directory to identify
    the environment.  Exits zero when egress is restored; exits non-zero
    if the unlock operation fails.

    If the environment is already unlocked, exits zero with an informational
    message (idempotent).

    \b
    Examples:
      microjail unlock
    """
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

    if not state.locked:
        typer.echo(f"Environment '{state.name}' is already unlocked.")
        return

    try:
        unlock_egress(state.name)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    state.locked = False
    try:
        state.to_json(workspace)
    except OSError as exc:
        typer.echo(
            f"Warning: Could not update state file after unlock: {exc}", err=True
        )

    typer.echo(f"Environment '{state.name}' unlocked.")
