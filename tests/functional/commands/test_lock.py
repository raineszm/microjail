from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from microjail.cli import app
from microjail.lockdown import CapabilityError, GateError, Lockdown

if TYPE_CHECKING:
    from pathlib import Path


def create_microjail_config(project: Path) -> Path:
    config = project / ".microjail" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        f"name: test-jail\nproject_path: {project}\nlockdown:\n  caps: []\n  gates: []\n",
        encoding="utf-8",
    )
    return config


@pytest.fixture
def microjail_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    create_microjail_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def fail_lockdown(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    def ensure(self: Lockdown) -> None:
        raise failure

    monkeypatch.setattr(Lockdown, "ensure", ensure)


def test_lock_reports_success(microjail_project: Path) -> None:
    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert "locked" in result.stdout.lower()


def test_lock_rejects_unexpected_arguments() -> None:
    result = CliRunner().invoke(app, ["lock", "workload"])

    assert result.exit_code != 0
    assert "unexpected" in result.stderr.lower()


def test_lock_warns_on_capability_failure_by_default(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    fail_lockdown(monkeypatch, CapabilityError(name="local-inference"))

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 0
    assert "failed to provide capabilities" in result.stderr.lower()
    assert "local-inference" in result.stderr


def test_lock_reports_gate_failure(
    monkeypatch: pytest.MonkeyPatch, microjail_project: Path
) -> None:
    fail_lockdown(monkeypatch, GateError(name="network-egress"))

    result = CliRunner().invoke(app, ["lock"])

    assert result.exit_code == 1
    assert "failed to enforce gates" in result.stderr.lower()
    assert "network-egress" in result.stderr
    assert "GateError" not in result.stderr
