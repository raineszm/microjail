"""Unit tests for the config-readonly gate.

Constitution requirement: tests MUST demonstrate the gate BLOCKS when the
config file is world-writable.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from microjail.gates import GateResult, run_all_gates
from microjail.gates.config_readonly import check_config_readonly
from microjail.state import EnvironmentState

if TYPE_CHECKING:
    from pathlib import Path


def test_config_readonly_gate_passes_when_not_world_writable(tmp_path: Path) -> None:
    """Gate PASSES when opencode.jsonc exists and is not world-writable."""
    config = tmp_path / "opencode.jsonc"
    config.write_text("{}")
    config.chmod(0o644)
    result = check_config_readonly(tmp_path)
    assert isinstance(result, GateResult)
    assert result.passed is True
    assert result.name == "config-readonly"


def test_config_readonly_gate_blocks_when_world_writable(tmp_path: Path) -> None:
    """Gate FAILS (blocks workload) when opencode.jsonc is world-writable.

    Constitution-mandated blocking case.
    """
    config = tmp_path / "opencode.jsonc"
    config.write_text("{}")
    config.chmod(0o666)
    result = check_config_readonly(tmp_path)
    assert result.passed is False
    assert "world-writable" in result.message
    assert "chmod" in result.message


def test_config_readonly_gate_blocks_when_file_missing(tmp_path: Path) -> None:
    """Gate FAILS when opencode.jsonc does not exist."""
    result = check_config_readonly(tmp_path)
    assert result.passed is False
    assert "not found" in result.message


def test_config_readonly_gate_passes_with_owner_only_write(tmp_path: Path) -> None:
    """Gate PASSES when only the owner can write (0o644 or 0o600)."""
    config = tmp_path / "opencode.jsonc"
    config.write_text("{}")
    config.chmod(0o600)
    result = check_config_readonly(tmp_path)
    assert result.passed is True


def test_config_readonly_absent_for_omp_agent(tmp_path: Path) -> None:
    """config-readonly gate is NOT evaluated when agent is "omp"."""
    state = EnvironmentState(
        name="testenv",
        base_image="ubuntu@24.04",
        inference=None,
        agent="omp",
        socket_url=None,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    results = run_all_gates(state, tmp_path)
    assert not any(r.name == "config-readonly" for r in results)


def test_config_readonly_absent_for_none_agent(tmp_path: Path) -> None:
    """config-readonly gate is NOT evaluated when agent is None."""
    state = EnvironmentState(
        name="testenv",
        base_image="ubuntu@24.04",
        inference=None,
        agent=None,
        socket_url=None,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    results = run_all_gates(state, tmp_path)
    assert not any(r.name == "config-readonly" for r in results)
