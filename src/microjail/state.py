"""Environment state persistence.

Writes and reads ``.microjail/state.json`` in the workspace directory so
downstream commands (``run``, ``unlock``) can locate the environment and
its configuration without the user re-specifying flags.
"""

from typing import TYPE_CHECKING

import msgspec
from msgspec import field

if TYPE_CHECKING:
    from pathlib import Path

STATE_DIR = ".microjail"
STATE_FILE = "state.json"


class State(msgspec.Struct):
    """Persisted record of a created microjail environment."""

    name: str
    """Workshop environment name."""

    base_image: str
    """LXD base image, e.g. ``ubuntu@26.04``."""

    inference: str | None
    """Inference backend (e.g. ``"llama-cpp"``), or ``None``."""

    agent: str | None
    """Agent harness (e.g. ``"opencode"``), or ``None``."""

    socket_url: str | None
    """Inference endpoint URL, or ``None`` if no inference backend configured."""

    locked: bool = field(default=False)
    """Whether the environment's network egress is currently severed.

    Set to ``True`` by ``microjail lock`` (and by ``microjail run`` via the
    same locking logic). Set back to ``False`` by ``microjail unlock`` (and
    by ``microjail run`` after the workload exits).
    """

    def dump(self, workspace: Path) -> None:
        """Write state to ``<workspace>/.microjail/state.json``.

        Creates the ``.microjail/`` directory if it does not exist.
        Raises :exc:`OSError` if the directory cannot be created or the file
        cannot be written — the caller is responsible for handling this.
        """
        state_dir = workspace / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / STATE_FILE
        state_path.write_bytes(msgspec.json.encode(self))

    @classmethod
    def from_json(cls, workspace: Path) -> State:
        """Read state from ``<workspace>/.microjail/state.json``.

        Raises :exc:`FileNotFoundError` if the state file does not exist.
        Raises :exc:`ValueError` if the file is not valid JSON or is missing
        required fields.
        """
        state_path = workspace / STATE_DIR / STATE_FILE
        return msgspec.json.decode(state_path.read_bytes(), type=cls)
