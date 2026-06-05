"""Implementation of ``microjail unlock``.

Restores network egress to the container and marks the environment as unlocked
in the state file.  Idempotent: calling on an already-unlocked environment
exits zero with an informational message (FR-014).
"""

from pathlib import Path

import typer

from microjail.output import err, warn
from microjail.state import State, StateError
from microjail.wrappers.lxd import unlock_egress


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
    try:
        state = State.load(workspace)
    except StateError as exc:
        err(str(exc))

    if not state.locked:
        typer.echo(f"Environment '{state.name}' is already unlocked.")
        return

    try:
        unlock_egress(state.name)
    except RuntimeError as exc:
        err(str(exc))

    state.locked = False
    try:
        state.to_json(workspace)
    except OSError as exc:
        warn(f"Could not update state file after unlock: {exc}")

    typer.echo(f"Environment '{state.name}' unlocked.")
