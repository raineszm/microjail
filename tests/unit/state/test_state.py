"""Unit tests for EnvironmentState serialisation round-trip."""

from typing import TYPE_CHECKING

import msgspec
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
    }
    defaults.update(overrides)
    return msgspec.convert(defaults, State)  # type: ignore[arg-type]


def test_round_trip_full(tmp_workspace: Path) -> None:
    """Full state survives write → read without data loss."""
    original = _make_state()
    original.dump(tmp_workspace)

    state_path = tmp_workspace / STATE_DIR / STATE_FILE
    assert state_path.exists(), "state.json was not created"

    loaded = State.from_json(tmp_workspace)
    assert loaded.name == original.name
    assert loaded.base_image == original.base_image
    assert loaded.inference == original.inference
    assert loaded.agent == original.agent
    assert loaded.socket_url == original.socket_url


def test_round_trip_null_inference_agent(tmp_workspace: Path) -> None:
    """State with null inference/agent/socket_url survives round-trip."""
    original = _make_state(inference=None, agent=None, socket_url=None)
    original.dump(tmp_workspace)

    loaded = State.from_json(tmp_workspace)
    assert loaded.inference is None
    assert loaded.agent is None
    assert loaded.socket_url is None


def test_missing_state_file_raises(tmp_workspace: Path) -> None:
    """from_json raises FileNotFoundError when state.json is absent."""
    with pytest.raises(FileNotFoundError):
        State.from_json(tmp_workspace)


def test_invalid_json_raises(tmp_workspace: Path) -> None:
    """from_json raises msgspec.DecodeError when state.json is malformed JSON."""
    import msgspec

    state_dir = tmp_workspace / STATE_DIR
    state_dir.mkdir()
    (state_dir / STATE_FILE).write_text("not json")

    with pytest.raises(msgspec.DecodeError):
        State.from_json(tmp_workspace)
