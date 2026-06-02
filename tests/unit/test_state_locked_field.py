"""Unit tests for the ``locked`` field in :class:`~microjail.state.EnvironmentState`.

Verifies round-trip serialisation, default value, and that existing state
files without the ``locked`` key deserialise without error (backwards
compatibility for environments created before this field was added).
"""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from microjail.state import EnvironmentState

if TYPE_CHECKING:
    from pathlib import Path


def _base_state(*, locked: bool = False) -> EnvironmentState:
    return EnvironmentState(
        name="test-env",
        base_image="ubuntu@26.04",
        inference=None,
        agent=None,
        socket_url=None,
        created_at=datetime(2026, 6, 2, 10, 0, 0, tzinfo=UTC),
        locked=locked,
    )


def test_locked_field_defaults_to_false() -> None:
    """``locked`` defaults to False on a freshly created state object."""
    state = _base_state()
    assert state.locked is False


def test_locked_field_round_trip_false(tmp_path: Path) -> None:
    """``locked=False`` survives a write/read cycle."""
    state = _base_state(locked=False)
    state.to_json(tmp_path)
    loaded = EnvironmentState.from_json(tmp_path)
    assert loaded.locked is False


def test_locked_field_round_trip_true(tmp_path: Path) -> None:
    """``locked=True`` survives a write/read cycle."""
    state = _base_state(locked=True)
    state.to_json(tmp_path)
    loaded = EnvironmentState.from_json(tmp_path)
    assert loaded.locked is True


def test_locked_field_persisted_in_json(tmp_path: Path) -> None:
    """The ``locked`` key is present in the written JSON."""
    state = _base_state(locked=True)
    state.to_json(tmp_path)
    raw = json.loads((tmp_path / ".microjail" / "state.json").read_text())
    assert raw["locked"] is True


def test_locked_field_absent_in_old_state_file_defaults_to_false(
    tmp_path: Path,
) -> None:
    """State files without ``locked`` (written before this field was added)
    deserialise with ``locked=False`` (backwards compatibility).
    """
    state = _base_state()
    state.to_json(tmp_path)
    # Remove the locked key to simulate an old state file.
    state_path = tmp_path / ".microjail" / "state.json"
    raw = json.loads(state_path.read_text())
    del raw["locked"]
    state_path.write_text(json.dumps(raw))

    loaded = EnvironmentState.from_json(tmp_path)
    assert loaded.locked is False
