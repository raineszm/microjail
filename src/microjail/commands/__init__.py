"""CLI command implementations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from microjail.output import err
from microjail.state import State


def load_state_or_exit(workspace: Path) -> State:
    """Load State from *workspace*/.microjail/state.json, exiting on failure.

    Calls ``err()`` (which raises ``typer.Exit``) when:

    - :exc:`FileNotFoundError`: no environment initialised in this directory.
    - :exc:`RuntimeError`: state file is corrupt or environment is inconsistent.
    """
    try:
        return State.from_json(workspace)
    except FileNotFoundError:
        err(
            "No microjail environment found in the current directory."
            " Run 'microjail init' first."
        )
    except RuntimeError as exc:
        err(str(exc))
