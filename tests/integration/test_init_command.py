"""Integration tests for ``microjail init``.

Requires a live Workshop + LXD installation. Skip with::

    pytest -m "not lxd"

Each test receives a ``workspace`` fixture that provides an isolated temp
directory as the working directory. Environment teardown is handled by a
dedicated ``workshop_env`` fixture that yields the environment name and
removes it unconditionally on exit — the test body never needs try/finally.
"""

import json
import subprocess
import uuid
from typing import TYPE_CHECKING

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

from microjail.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_name(prefix: str) -> str:
    """Return a unique, Workshop-safe environment name (max 63 chars)."""
    suffix = uuid.uuid4().hex[:8]
    return f"{prefix}-{suffix}"


def _workshop_info_ok(name: str, project_dir: Path) -> bool:
    """Return True if ``workshop info <name>`` exits 0."""
    result = subprocess.run(
        ["workshop", "info", name, "--project", str(project_dir)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Change cwd to a fresh temp directory for the duration of the test."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def us1_env(workspace: Path) -> Generator[str]:
    """Create a US1 (--inference llama-cpp --agent opencode) environment.

    Yields the environment name. Removes the environment on teardown
    regardless of whether the test passed or failed.
    """
    name = _unique_name("mj-us1")
    result = runner.invoke(
        app,
        ["init", name, "--inference", "llama-cpp", "--agent", "opencode"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"Fixture init failed:\n{result.output}"
    yield name
    subprocess.run(
        ["workshop", "remove", name, "--project", str(workspace)],
        capture_output=True,
        check=False,
    )


@pytest.fixture
def us2_env(workspace: Path) -> Generator[str]:
    """Create a US2 (bare, no flags) environment.

    Yields the environment name. Removes the environment on teardown.
    """
    name = _unique_name("mj-us2")
    try:
        result = runner.invoke(app, ["init", name], catch_exceptions=False)
        assert result.exit_code == 0, f"Fixture init failed:\n{result.output}"
        yield name
    finally:
        subprocess.run(
            ["workshop", "remove", name, "--project", str(workspace)],
            capture_output=True,
            check=False,
        )


# ---------------------------------------------------------------------------
# T015 — User Story 1: full init (--inference llama-cpp --agent opencode)
# ---------------------------------------------------------------------------


@pytest.mark.lxd
def test_us1_full_init_exit_zero(workspace: Path) -> None:
    """Microjail init <name> --inference llama-cpp --agent opencode exits 0."""
    name = _unique_name("mj-us1")
    result = runner.invoke(
        app,
        ["init", name, "--inference", "llama-cpp", "--agent", "opencode"],
        catch_exceptions=False,
    )
    subprocess.run(
        ["workshop", "remove", name, "--project", str(workspace)],
        capture_output=True,
        check=False,
    )
    assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"


@pytest.mark.lxd
def test_us1_definition_yaml_written(workspace: Path, us1_env: str) -> None:
    """Workshop definition is written at .workshop/<name>.yaml."""
    assert (workspace / ".workshop" / f"{us1_env}.yaml").exists()


@pytest.mark.lxd
def test_us1_opencode_jsonc_written(workspace: Path, us1_env: str) -> None:
    """opencode.jsonc is written when --agent opencode is specified."""
    assert (workspace / "opencode.jsonc").exists()


@pytest.mark.lxd
def test_us1_state_json_written(workspace: Path, us1_env: str) -> None:
    """state.json is written with correct name, inference, and agent fields."""
    state_path = workspace / ".microjail" / "state.json"
    assert state_path.exists(), "state.json not written"
    state = json.loads(state_path.read_text())
    assert state["name"] == us1_env
    assert state["inference"] == "llama-cpp"
    assert state["agent"] == "opencode"


@pytest.mark.lxd
def test_us1_workshop_env_exists(workspace: Path, us1_env: str) -> None:
    """Workshop info exits 0 after successful init (invariant 1)."""
    assert _workshop_info_ok(us1_env, workspace), (
        f"Workshop environment '{us1_env}' not found after init"
    )


@pytest.mark.lxd
def test_us1_no_remote_providers_enabled(workspace: Path, us1_env: str) -> None:
    """opencode.jsonc has no enabled remote provider entries (invariant 3)."""
    cfg = json.loads((workspace / "opencode.jsonc").read_text())
    remote = {k: v for k, v in cfg["provider"].items() if k != "llama.cpp"}
    bad = {k: v for k, v in remote.items() if v.get("enabled") is not False}
    assert not bad, f"Remote providers not disabled: {bad}"


@pytest.mark.lxd
def test_us1_duplicate_name_rejected(workspace: Path, us1_env: str) -> None:
    """Second init with same name exits 2 with 'already exists' message."""
    result = runner.invoke(app, ["init", us1_env], catch_exceptions=False)
    assert result.exit_code == 2
    assert "already exists" in result.output


# ---------------------------------------------------------------------------
# T017 — User Story 2: bare init (no flags)
# ---------------------------------------------------------------------------


@pytest.mark.lxd
def test_us2_bare_init_exit_zero(workspace: Path) -> None:
    """Microjail init <name> (no flags) exits 0."""
    name = _unique_name("mj-us2")
    result = runner.invoke(app, ["init", name], catch_exceptions=False)
    subprocess.run(
        ["workshop", "remove", name, "--project", str(workspace)],
        capture_output=True,
        check=False,
    )
    assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"


@pytest.mark.lxd
def test_us2_no_opencode_jsonc(workspace: Path, us2_env: str) -> None:
    """opencode.jsonc is NOT written when --agent is not specified."""
    assert not (workspace / "opencode.jsonc").exists(), (
        "opencode.jsonc should not be written for bare init"
    )


@pytest.mark.lxd
def test_us2_workshop_yaml_empty_sdks(workspace: Path, us2_env: str) -> None:
    """Workshop definition has empty sdks list for bare init."""
    yaml = YAML()
    doc = yaml.load((workspace / ".workshop" / f"{us2_env}.yaml").read_text())
    sdks = doc.get("sdks") or []
    assert sdks == [], f"Expected empty sdks, got: {sdks}"


@pytest.mark.lxd
def test_us2_state_json_null_fields(workspace: Path, us2_env: str) -> None:
    """state.json has null inference, agent, and socket_url for bare init."""
    state = json.loads((workspace / ".microjail" / "state.json").read_text())
    assert state["inference"] is None
    assert state["agent"] is None
    assert state["socket_url"] is None


@pytest.mark.lxd
def test_us2_workshop_env_exists(workspace: Path, us2_env: str) -> None:
    """Workshop info exits 0 after bare init."""
    assert _workshop_info_ok(us2_env, workspace), (
        f"Workshop environment '{us2_env}' not found after bare init"
    )


# ---------------------------------------------------------------------------
# T018 — --force reinitialises an existing environment via workshop refresh
# ---------------------------------------------------------------------------


@pytest.mark.lxd
def test_force_reinit_exits_zero(workspace: Path, us1_env: str) -> None:
    """Microjail init <name> --force exits 0 when environment already exists."""
    result = runner.invoke(
        app,
        ["init", us1_env, "--inference", "llama-cpp", "--agent", "opencode", "--force"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"


@pytest.mark.lxd
def test_force_reinit_env_still_exists(workspace: Path, us1_env: str) -> None:
    """Workshop environment is still reachable after --force reinit."""
    runner.invoke(
        app,
        ["init", us1_env, "--inference", "llama-cpp", "--agent", "opencode", "--force"],
        catch_exceptions=False,
    )
    assert _workshop_info_ok(us1_env, workspace), (
        f"Workshop environment '{us1_env}' not found after --force reinit"
    )


@pytest.mark.lxd
def test_force_reinit_state_updated(workspace: Path, us1_env: str) -> None:
    """state.json is rewritten with a fresh created_at timestamp after --force reinit."""
    state_before = json.loads((workspace / ".microjail" / "state.json").read_text())
    result = runner.invoke(
        app,
        ["init", us1_env, "--inference", "llama-cpp", "--agent", "opencode", "--force"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"
    state_after = json.loads((workspace / ".microjail" / "state.json").read_text())
    assert state_after["created_at"] >= state_before["created_at"], (
        "state.json created_at was not updated after --force reinit"
    )
