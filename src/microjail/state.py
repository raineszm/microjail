"""Environment state persistence.

Writes and reads ``.microjail/state.json`` in the workspace directory so
downstream commands (``run``, ``unlock``) can locate the environment and
its configuration without the user re-specifying flags.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

STATE_DIR = ".microjail"
STATE_FILE = "state.json"


class StateError(Exception):
    """Base class for state file errors."""


class StateNotFoundError(StateError):
    """Raised when no ``.microjail/state.json`` exists in the workspace."""


class StateParseError(StateError):
    """Raised when the state file exists but cannot be parsed."""


@dataclass
class State:
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

    def to_json(self, workspace: Path) -> None:
        """Write state to ``<workspace>/.microjail/state.json``.

        Creates the ``.microjail/`` directory if it does not exist.
        Raises :exc:`OSError` if the directory cannot be created or the file
        cannot be written — the caller is responsible for handling this.
        """
        state_dir = workspace / STATE_DIR
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / STATE_FILE
        payload = asdict(self)
        state_path.write_text(json.dumps(payload, indent=4))

    @classmethod
    def from_json(cls, workspace: Path) -> State:
        """Read state from ``<workspace>/.microjail/state.json``.

        Raises :exc:`FileNotFoundError` if the state file does not exist.
        Raises :exc:`ValueError` if the file cannot be parsed.
        """
        state_path = workspace / STATE_DIR / STATE_FILE
        try:
            raw = json.loads(state_path.read_text())
        except json.JSONDecodeError as exc:
            msg = f"State file at {state_path} is not valid JSON: {exc}"
            raise ValueError(msg) from exc
        try:
            return cls(
                name=raw["name"],
                base_image=raw["base_image"],
                inference=raw.get("inference"),
                agent=raw.get("agent"),
                socket_url=raw.get("socket_url"),
                locked=bool(raw.get("locked", False)),
            )
        except KeyError as exc:
            msg = f"State file at {state_path} is missing required field: {exc}"
            raise ValueError(msg) from exc

    @classmethod
    def load(cls, workspace: Path) -> State:
        """Load state from *workspace*, raising bespoke errors on failure.

        Raises :exc:`StateNotFoundError` if no ``.microjail/state.json`` is
        present.  Raises :exc:`StateParseError` if the file cannot be parsed.
        """
        state_path = workspace / STATE_DIR / STATE_FILE
        if not state_path.exists():
            raise StateNotFoundError(
                "No microjail environment found in the current directory. "
                "Run 'microjail init' first."
            )
        try:
            return cls.from_json(workspace)
        except ValueError as exc:
            raise StateParseError(f"Cannot read state file: {exc}") from exc
