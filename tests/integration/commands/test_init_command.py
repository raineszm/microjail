"""Integration tests for ``microjail init``.

Requires a live Workshop + LXD installation.  Tests are skipped automatically
when the required services are unavailable; long-running tests (those that
create containers) additionally require ``--run-long``.

Each test receives a ``workspace`` fixture providing an isolated temp directory
as the working directory.  Environment teardown is handled by ``us1_env`` and
``us2_env`` fixtures that yield the environment name and remove it
unconditionally on exit — the test body never needs try/finally.

Teardown calls ``await_env_removed`` after ``workshop remove`` to block until
LXD has fully deleted the container.  This prevents the rapid-remove/launch
race that causes subsequent ``workshop launch`` calls to block indefinitely.
"""

import json
import subprocess
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from microjail.cli import app
from tests.integration.commands._helpers import await_env_removed

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

    Yields the environment name.  Removes the environment on teardown
    regardless of whether the test passed or failed, then waits until LXD has
    fully deleted the container before returning so the next test's
    ``workshop launch`` does not race against pending cleanup.
    """
    name = _unique_name("mj-us1")
    try:
        result = runner.invoke(
            app,
            ["init", name, "--inference", "llama-cpp", "--agent", "opencode"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, f"Fixture init failed:\n{result.output}"
        yield name
    finally:
        subprocess.run(
            ["workshop", "remove", name, "--project", str(workspace)],
            capture_output=True,
            check=False,
        )
        await_env_removed(name)


@pytest.fixture
def us2_env(workspace: Path) -> Generator[str]:
    """Create a US2 (bare, no flags) environment.

    Same teardown guarantee as ``us1_env``.
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
        await_env_removed(name)


# ---------------------------------------------------------------------------
# T015 — User Story 1: full init (--inference llama-cpp --agent opencode)
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
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
    await_env_removed(name)
    assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_definition_yaml_written(workspace: Path, us1_env: str) -> None:
    """Workshop definition is written at .workshop/<name>.yaml."""
    assert (workspace / ".workshop" / f"{us1_env}.yaml").exists()


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_opencode_jsonc_written(workspace: Path, us1_env: str) -> None:
    """opencode.jsonc is written when --agent opencode is specified."""
    assert (workspace / "opencode.jsonc").exists()


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_state_json_written(workspace: Path, us1_env: str) -> None:
    """state.json is written with correct name, inference, and agent fields."""
    state_path = workspace / ".microjail" / "state.json"
    assert state_path.exists(), "state.json not written"
    state = json.loads(state_path.read_text())
    assert state["name"] == us1_env
    assert state["inference"] == "llama-cpp"
    assert state["agent"] == "opencode"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_workshop_env_exists(workspace: Path, us1_env: str) -> None:
    """Workshop info exits 0 after successful init (invariant 1)."""
    assert _workshop_info_ok(us1_env, workspace), (
        f"Workshop environment '{us1_env}' not found after init"
    )


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_no_remote_providers_enabled(workspace: Path, us1_env: str) -> None:
    """opencode.jsonc has no enabled remote provider entries (invariant 3)."""
    cfg = json.loads((workspace / "opencode.jsonc").read_text())
    remote = {k: v for k, v in cfg["provider"].items() if k != "llama.cpp"}
    bad = {k: v for k, v in remote.items() if v.get("enabled") is not False}
    assert not bad, f"Remote providers not disabled: {bad}"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_duplicate_name_rejected(workspace: Path, us1_env: str) -> None:
    """Second init with same name exits 2 with 'already exists' message."""
    result = runner.invoke(app, ["init", us1_env], catch_exceptions=False)
    assert result.exit_code == 2
    assert "already exists" in result.output


# ---------------------------------------------------------------------------
# T017 — User Story 2: bare init (no flags)
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us2_bare_init_exit_zero(workspace: Path) -> None:
    """Microjail init <name> (no flags) exits 0."""
    name = _unique_name("mj-us2")
    result = runner.invoke(app, ["init", name], catch_exceptions=False)
    subprocess.run(
        ["workshop", "remove", name, "--project", str(workspace)],
        capture_output=True,
        check=False,
    )
    await_env_removed(name)
    assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us2_no_opencode_jsonc(workspace: Path, us2_env: str) -> None:
    """opencode.jsonc is NOT written when --agent is not specified."""
    assert not (workspace / "opencode.jsonc").exists(), (
        "opencode.jsonc should not be written for bare init"
    )


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us2_workshop_yaml_empty_sdks(workspace: Path, us2_env: str) -> None:
    """Workshop definition has empty sdks list for bare init."""
    yaml = YAML()
    doc = yaml.load((workspace / ".workshop" / f"{us2_env}.yaml").read_text())
    sdks = doc.get("sdks") or []
    assert sdks == [], f"Expected empty sdks, got: {sdks}"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us2_state_json_null_fields(workspace: Path, us2_env: str) -> None:
    """state.json has null inference, agent, and socket_url for bare init."""
    state = json.loads((workspace / ".microjail" / "state.json").read_text())
    assert state["inference"] is None
    assert state["agent"] is None
    assert state["socket_url"] is None


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us2_workshop_env_exists(workspace: Path, us2_env: str) -> None:
    """Workshop info exits 0 after bare init."""
    assert _workshop_info_ok(us2_env, workspace), (
        f"Workshop environment '{us2_env}' not found after bare init"
    )


# ---------------------------------------------------------------------------
# T018 — --force reinitialises an existing environment via workshop refresh
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_force_reinit_exits_zero(workspace: Path, us1_env: str) -> None:
    """Microjail init <name> --force exits 0 when environment already exists."""
    result = runner.invoke(
        app,
        ["init", us1_env, "--inference", "llama-cpp", "--agent", "opencode", "--force"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
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


# ---------------------------------------------------------------------------
# T015 — Tunnel YAML structure assertions
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_workshop_yaml_has_tunnel_slot(workspace: Path, us1_env: str) -> None:
    """Workshop definition contains system SDK with tunnel slot when --inference is set."""
    yaml_path = workspace / ".workshop" / f"{us1_env}.yaml"
    doc = YAML().load(yaml_path.read_text())
    system_sdk = next((s for s in doc["sdks"] if s["name"] == "system"), None)
    assert system_sdk is not None, "system SDK missing"
    assert system_sdk["slots"]["llama-cpp"]["interface"] == "tunnel"
    assert system_sdk["slots"]["llama-cpp"]["endpoint"] == "localhost:8080"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_workshop_yaml_has_tunnel_plug(workspace: Path, us1_env: str) -> None:
    """Workshop definition contains project SDK with tunnel plug when --inference is set."""
    yaml_path = workspace / ".workshop" / f"{us1_env}.yaml"
    doc = YAML().load(yaml_path.read_text())
    llama_sdk = next((s for s in doc["sdks"] if s["name"] == "llama-cpp"), None)
    assert llama_sdk is not None, "llama-cpp SDK missing"
    assert llama_sdk["plugs"]["llama-cpp"]["interface"] == "tunnel"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us2_workshop_yaml_no_tunnel_entries(workspace: Path, us2_env: str) -> None:
    """Workshop definition has no tunnel entries when --inference is not set."""
    yaml_path = workspace / ".workshop" / f"{us2_env}.yaml"
    yaml_str = yaml_path.read_text()
    doc = YAML().load(yaml_str)
    sdk_names = [s["name"] for s in doc.get("sdks", [])]
    assert "system" not in sdk_names
    assert "llama-cpp" not in sdk_names
    for forbidden in ("tunnel", "plugs", "slots"):
        assert forbidden not in yaml_str, f"Forbidden key '{forbidden}' found"


# ---------------------------------------------------------------------------
# T033 — State file assertions
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us1_state_json_has_http_socket_url(workspace: Path, us1_env: str) -> None:
    """state.json contains HTTP URL for socket_url when --inference is set."""
    state = json.loads((workspace / ".microjail" / "state.json").read_text())
    assert state["socket_url"] == "http://127.0.0.1:8080/v1"


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_us2_state_json_null_socket_url(workspace: Path, us2_env: str) -> None:
    """state.json has null socket_url when --inference is not set."""
    state = json.loads((workspace / ".microjail" / "state.json").read_text())
    assert state["socket_url"] is None


# ---------------------------------------------------------------------------
# T017 — Force re-init refreshes tunnel config
# ---------------------------------------------------------------------------


@pytest.mark.lxd
@pytest.mark.workshop
@pytest.mark.long_running
def test_force_reinit_preserves_tunnel_config(workspace: Path, us1_env: str) -> None:
    """--force re-initialisation preserves tunnel config in workshop.yaml."""
    result = runner.invoke(
        app,
        ["init", us1_env, "--inference", "llama-cpp", "--agent", "opencode", "--force"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"Non-zero exit:\n{result.output}"
    yaml_path = workspace / ".workshop" / f"{us1_env}.yaml"
    doc = YAML().load(yaml_path.read_text())
    sdk_names = [s["name"] for s in doc["sdks"]]
    assert "system" in sdk_names
    assert "llama-cpp" in sdk_names
