"""Unit tests for the run log writer (``_write_run_log``).

Verifies:
- A log entry is written on a successful run.
- A log entry is written when the workload exits non-zero.
- Multiple runs are appended (log is append-only, not overwritten).
- Each entry contains the mandatory fields: environment, workload, started_at,
  completed_at, gates, exit_code.
"""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from microjail.commands.run import _write_run_log
from microjail.state import EnvironmentState

if TYPE_CHECKING:
    from pathlib import Path


def _make_state() -> EnvironmentState:
    return EnvironmentState(
        name="test-env",
        base_image="ubuntu@26.04",
        inference=None,
        agent=None,
        socket_url=None,
        created_at=datetime(2026, 6, 2, 10, 0, 0, tzinfo=UTC),
        locked=True,
    )


def _start_time() -> datetime:
    return datetime(2026, 6, 2, 11, 0, 0, tzinfo=UTC)


def _init_microjail_dir(tmp_path: Path) -> None:
    (tmp_path / ".microjail").mkdir(exist_ok=True)


def test_run_log_written_on_success(tmp_path: Path) -> None:
    """A JSONL entry is appended to run-log.jsonl on a zero-exit run."""
    _init_microjail_dir(tmp_path)
    state = _make_state()
    _write_run_log(tmp_path, state, ["echo", "hello"], _start_time(), [], 0)
    log_path = tmp_path / ".microjail" / "run-log.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text().strip())
    assert entry["exit_code"] == 0
    assert entry["workload"] == ["echo", "hello"]


def test_run_log_written_on_nonzero_exit(tmp_path: Path) -> None:
    """A JSONL entry is written even when the workload exits non-zero."""
    _init_microjail_dir(tmp_path)
    state = _make_state()
    _write_run_log(tmp_path, state, ["false"], _start_time(), [], 1)
    log_path = tmp_path / ".microjail" / "run-log.jsonl"
    entry = json.loads(log_path.read_text().strip())
    assert entry["exit_code"] == 1


def test_run_log_is_append_only(tmp_path: Path) -> None:
    """Multiple invocations append new lines; prior lines are preserved."""
    _init_microjail_dir(tmp_path)
    state = _make_state()
    _write_run_log(tmp_path, state, ["echo", "first"], _start_time(), [], 0)
    _write_run_log(tmp_path, state, ["echo", "second"], _start_time(), [], 0)
    log_path = tmp_path / ".microjail" / "run-log.jsonl"
    lines = [l for l in log_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["workload"] == ["echo", "first"]
    assert second["workload"] == ["echo", "second"]


def test_run_log_entry_contains_mandatory_fields(tmp_path: Path) -> None:
    """Each entry contains environment, workload, started_at, completed_at, gates, exit_code."""
    _init_microjail_dir(tmp_path)
    state = _make_state()
    gate_results = [{"name": "egress", "passed": True, "message": "Egress down"}]
    _write_run_log(tmp_path, state, ["ls"], _start_time(), gate_results, 0)
    log_path = tmp_path / ".microjail" / "run-log.jsonl"
    entry = json.loads(log_path.read_text().strip())
    for field in (
        "environment",
        "workload",
        "started_at",
        "completed_at",
        "gates",
        "exit_code",
    ):
        assert field in entry, f"Missing field: {field}"
    assert entry["environment"] == "test-env"
    assert entry["gates"] == gate_results


def test_run_log_raises_on_unwritable_dir(tmp_path: Path) -> None:
    """OSError is raised when the log directory is not writable."""
    state = _make_state()
    # .microjail dir does not exist — open() should raise OSError.
    with pytest.raises(OSError):
        _write_run_log(tmp_path, state, ["ls"], _start_time(), [], 0)
