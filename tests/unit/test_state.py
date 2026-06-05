"""Unit tests for EnvironmentState serialisation round-trip."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from microjail.state import STATE_DIR, STATE_FILE, State

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    return tmp_path


def _make_state(**overrides: object) -> State:
    defaults: dict[str, object] = {
        "name": "testenv",
        "base_image": "ubuntu@26.04",
        "inference": "llama-cpp",
        "agent": "opencode",
        "socket_url": "http://127.0.0.1:8080/v1",
        "created_at": datetime(2026, 5, 29, 15, 41, 52, tzinfo=UTC),
    }
    defaults.update(overrides)
    return State(**defaults)  # type: ignore[arg-type]


def test_round_trip_full(tmp_workspace: Path) -> None:
    """Full state survives write → read without data loss."""
    original = _make_state()
    original.to_json(tmp_workspace)

    state_path = tmp_workspace / STATE_DIR / STATE_FILE
    assert state_path.exists(), "state.json was not created"

    loaded = State.from_json(tmp_workspace)
    assert loaded.name == original.name
    assert loaded.base_image == original.base_image
    assert loaded.inference == original.inference
    assert loaded.agent == original.agent
    assert loaded.socket_url == original.socket_url
    assert loaded.created_at == original.created_at


def test_round_trip_null_inference_agent(tmp_workspace: Path) -> None:
    """State with null inference/agent/socket_url survives round-trip."""
    original = _make_state(inference=None, agent=None, socket_url=None)
    original.to_json(tmp_workspace)

    loaded = State.from_json(tmp_workspace)
    assert loaded.inference is None
    assert loaded.agent is None
    assert loaded.socket_url is None


def test_created_at_iso8601(tmp_workspace: Path) -> None:
    """created_at is serialised as ISO-8601 UTC string."""
    original = _make_state()
    original.to_json(tmp_workspace)

    raw = json.loads((tmp_workspace / STATE_DIR / STATE_FILE).read_text())
    assert raw["created_at"] == "2026-05-29T15:41:52Z"


def test_missing_state_file_raises(tmp_workspace: Path) -> None:
    """from_json raises FileNotFoundError when state.json is absent."""
    with pytest.raises(FileNotFoundError):
        State.from_json(tmp_workspace)


def test_invalid_json_raises(tmp_workspace: Path) -> None:
    """from_json raises ValueError when state.json is malformed JSON."""
    state_dir = tmp_workspace / STATE_DIR
    state_dir.mkdir()
    (state_dir / STATE_FILE).write_text("not json")

    with pytest.raises(ValueError, match="not valid JSON"):
        State.from_json(tmp_workspace)
