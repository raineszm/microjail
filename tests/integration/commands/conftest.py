"""Shared fixtures for integration command tests."""

from __future__ import annotations

import subprocess
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

import pytest
from typer.testing import CliRunner

from microjail.cli import app

runner = CliRunner()


def _unique_name(prefix: str) -> str:
    """Return a unique, Workshop-safe environment name (max 63 chars)."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def lxd_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[str]:
    """Create a bare microjail environment and chdir to its workspace.

    Yields the environment name. Restores egress and removes the Workshop
    environment on teardown regardless of test outcome.
    """
    monkeypatch.chdir(tmp_path)
    name = _unique_name("mj-int")
    try:
        result = runner.invoke(app, ["init", name], catch_exceptions=False)
        assert result.exit_code == 0, f"Fixture init failed:\n{result.output}"
        yield name
    finally:
        runner.invoke(app, ["unlock"])
        subprocess.run(
            ["workshop", "remove", name, "--project", str(tmp_path)],
            capture_output=True,
            check=False,
        )


@pytest.fixture
def lxd_inference_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[str]:
    """Create a microjail environment with --inference llama-cpp and chdir to workspace.

    Yields the environment name. Restores egress and removes the Workshop
    environment on teardown regardless of test outcome.
    """
    monkeypatch.chdir(tmp_path)
    name = _unique_name("mj-inf")
    try:
        result = runner.invoke(
            app,
            ["init", name, "--inference", "llama-cpp", "--agent", "opencode"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, f"Fixture init failed:\n{result.output}"
        yield name
    finally:
        runner.invoke(app, ["unlock"])
        subprocess.run(
            ["workshop", "remove", name, "--project", str(tmp_path)],
            capture_output=True,
            check=False,
        )
