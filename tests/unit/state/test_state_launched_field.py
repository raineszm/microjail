"""Unit tests for the ``launched`` field in :class:`~microjail.state.State`.

Verifies round-trip serialisation, default value, and that existing state
files without the ``launched`` key deserialise without error (backwards
compatibility for environments created before this field was added).
"""

import json
from typing import TYPE_CHECKING

from microjail.state import State

if TYPE_CHECKING:
    from pathlib import Path


def _base_state(*, launched: bool = True) -> State:
    return State(
        name="test-env",
        base_image="ubuntu@26.04",
        inference=None,
        agent=None,
        socket_url=None,
        launched=launched,
    )


def test_launched_field_defaults_to_true() -> None:
    """``launched`` defaults to True on a freshly created state object.

    All pre-existing state files were written after a successful launch, so
    the absence of the key should deserialise as True (backward compat).
    """
    state = State(
        name="test-env",
        base_image="ubuntu@26.04",
        inference=None,
        agent=None,
        socket_url=None,
    )
    assert state.launched is True


def test_launched_field_round_trip_false(tmp_path: Path) -> None:
    """``launched=False`` survives a write/read cycle."""
    state = _base_state(launched=False)
    state.dump(tmp_path)
    loaded = State.from_json(tmp_path)
    assert loaded.launched is False


def test_launched_field_round_trip_true(tmp_path: Path) -> None:
    """``launched=True`` survives a write/read cycle."""
    state = _base_state(launched=True)
    state.dump(tmp_path)
    loaded = State.from_json(tmp_path)
    assert loaded.launched is True


def test_launched_field_persisted_in_json(tmp_path: Path) -> None:
    """The ``launched`` key is present in the written JSON."""
    state = _base_state(launched=False)
    state.dump(tmp_path)
    raw = json.loads((tmp_path / ".microjail" / "state.json").read_text())
    assert raw["launched"] is False


def test_launched_field_absent_in_old_state_file_defaults_to_true(
    tmp_path: Path,
) -> None:
    """State files without ``launched`` (written before this field was added)
    deserialise with ``launched=True`` (backwards compatibility).

    The default is True because every pre-existing state file was written
    after a successful ``workshop launch + verify_exists``.
    """
    state = _base_state(launched=True)
    state.dump(tmp_path)
    # Remove the launched key to simulate an old state file.
    state_path = tmp_path / ".microjail" / "state.json"
    raw = json.loads(state_path.read_text())
    del raw["launched"]
    state_path.write_text(json.dumps(raw))

    loaded = State.from_json(tmp_path)
    assert loaded.launched is True
